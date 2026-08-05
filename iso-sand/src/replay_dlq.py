#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
replay_dlq.py — 死信队列重放工具（Phase 5 / 事件图谱治理）

读取 data/.dead_letter_queue.jsonl，将 original_event 按 v1.1 契约重新注入主总线：
    python3 src/replay_dlq.py --dry-run     # 只列出死信清单（默认推荐先跑）
    python3 src/replay_dlq.py               # 重放全部（剪除去重键 + 注入）
    python3 src/replay_dlq.py --keep-processed   # 只注入，不剪 processed_ids

关键语义（与 src/event_consumer.py 实现对齐，2026-08-04 实测确认）：
  1. consumer 在 _process_event 的 finally 中无条件 _mark_processed ——
     死信事件同样已被标记幂等去重。若直接重放同 event_id，consumer 会
     "🔁 幂等跳过"，重放无效。因此默认会把本次重放涉及的 event_id 先从
     processed_ids.jsonl 剪除（剪除前自动备份），再注入总线。
     --keep-processed 可跳过剪除（仅验证注入管道时使用）。
  2. 同一失败事件在 DLQ 中通常有 2 条记录（handler_registry 明细 +
     event_consumer 总账，original_event 相同）。重放按 event_id 去重，
     只注入 1 次，避免重复副作用。
  3. 注入保留原 event_id —— 事件被成功处理后，consumer 仍会按该 event_id
     去重，防止后续重复投递造成二次副作用（幂等语义不变）。

副作用说明：重放是真实注入（非只读）。注入后总线 consumer 会按 handler
链重新执行（如 interfaces.store → glue /store 会再次聚合写入沙漏+LMS+向量；
lms.feed → LMS /feed 塑形喂入）。请在业务低峰或确认依赖服务健康后执行。
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta

_BJT = timezone(timedelta(hours=8))

# 路径推导：本文件位于 <iso-sand>/src/，数据目录为 <iso-sand>/data/
_HERE = os.path.dirname(os.path.abspath(__file__))
_ISO_SAND_ROOT = os.path.dirname(_HERE)
_DEFAULT_DATA_DIR = os.path.join(_ISO_SAND_ROOT, "data")
_DEFAULT_DLQ = os.path.join(_DEFAULT_DATA_DIR, ".dead_letter_queue.jsonl")
_DEFAULT_BUS = os.path.join(_DEFAULT_DATA_DIR, "event_bus.jsonl")
_DEFAULT_PROCESSED = os.path.join(_DEFAULT_DATA_DIR, "processed_ids.jsonl")


def _now_iso() -> str:
    return datetime.now(_BJT).isoformat()


def load_dlq(dlq_path: str) -> list:
    """读取死信队列，返回 [{dlq_record, original_event, line_no}]"""
    entries = []
    if not os.path.exists(dlq_path):
        print(f"[replay] ⚠️ 死信文件不存在: {dlq_path}")
        return entries
    with open(dlq_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                print(f"[replay] ⚠️ 第 {line_no} 行非 JSON，跳过")
                continue
            oe = rec.get("original_event")
            if not isinstance(oe, dict):
                print(f"[replay] ⚠️ 第 {line_no} 行无 original_event（可能是老格式），跳过")
                continue
            entries.append({
                "line_no": line_no,
                "dlq": rec,
                "event": oe,
            })
    return entries


def dedupe_by_event_id(entries: list) -> list:
    """同一失败事件的 2 条 DLQ 记录（明细+总账）只保留 1 条。

    按 event_id 去重（无 event_id 的事件按 original_event 完整内容去重）。
    保留首次出现；返回 (去重后列表, 被去重数)。
    """
    seen = set()
    result = []
    dropped = 0
    for e in entries:
        ev = e["event"]
        key = ev.get("event_id") or json.dumps(ev, ensure_ascii=False, sort_keys=True)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        result.append(e)
    return result, dropped


def list_entries(entries: list) -> None:
    """dry-run 模式：列出死信清单"""
    print("=" * 78)
    print(f"📋 死信队列清单（共 {len(entries)} 条唯一事件，含 DLQ 明细行共 "
          f"{sum(1 for _ in entries)} 条）")
    print("=" * 78)
    for i, e in enumerate(entries, 1):
        ev = e["event"]
        dlq = e["dlq"]
        print(f"[{i}] event_id={ev.get('event_id') or '(无)'}")
        print(f"    event_type={ev.get('event_type')}  producer={ev.get('producer')}  "
              f"result={ev.get('result')}  trace_id={ev.get('trace_id')}")
        print(f"    死信原因: {dlq.get('detail', '')[:100]}")
        print(f"    死信时间: {dlq.get('t', '')}  (DLQ 行号 {e['line_no']})")
    print("-" * 78)
    print("提示: 默认重放会先剪除这些 event_id 的去重标记（processed_ids.jsonl，自动备份）再注入总线。")


def backup_processed(processed_path: str) -> str | None:
    """剪除前备份 processed_ids.jsonl，返回备份路径"""
    if not os.path.exists(processed_path):
        return None
    ts = datetime.now(_BJT).strftime("%Y%m%d-%H%M%S")
    bak = f"{processed_path}.bak.{ts}"
    shutil.copy2(processed_path, bak)
    return bak


def prune_processed(processed_path: str, replay_ids: set) -> int:
    """把 replay_ids 从 processed_ids.jsonl 剪除（原子重写），返回剪除条数"""
    if not replay_ids or not os.path.exists(processed_path):
        return 0
    keep_lines = []
    pruned = 0
    with open(processed_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                keep_lines.append(line + "\n")
                continue
            eid = rec.get("event_id")
            if eid and eid in replay_ids:
                pruned += 1
                continue
            keep_lines.append(line + "\n")

    # 原子重写（临时文件 + fsync + os.replace），与 consumer 的 atomic_rewrite 同语义
    from log_writer import LogWriter
    writer = LogWriter(processed_path)
    writer.atomic_rewrite(keep_lines)
    return pruned


def inject_events(bus_path: str, events: list) -> tuple:
    """按 v1.1 契约注入总线（LogWriter，保留原 event_id）。

    返回 (成功数, 失败数)。
    """
    from log_writer import LogWriter
    writer = LogWriter(bus_path)
    ok = 0
    failed = 0
    for ev in events:
        record = dict(ev)
        # 补齐契约字段（缺省补默认，不覆盖原值）
        record.setdefault("schema_version", "1.1")
        record.setdefault("trace_id", f"replay-dlq-{datetime.now(_BJT).strftime('%H%M%S')}")
        try:
            writer.write(record)  # validate=True：event_type/producer/result 必填 + result 枚举
            ok += 1
            print(f"[replay] ✅ 注入: {record.get('event_type')} "
                  f"event_id={record.get('event_id') or '(无)'} trace={record.get('trace_id')}")
        except ValueError as e:
            failed += 1
            print(f"[replay] ❌ 注入失败（契约校验不过）: {e}")
        except OSError as e:
            failed += 1
            print(f"[replay] ❌ 注入失败（IO）: {e}")
    return ok, failed


def main():
    ap = argparse.ArgumentParser(
        description="死信队列重放：读取 .dead_letter_queue.jsonl 重新注入主总线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="只列出死信清单，不注入、不改 processed_ids")
    ap.add_argument("--keep-processed", action="store_true",
                    help="注入但跳过 processed_ids 剪除（注意：同 event_id 会被 consumer 幂等跳过）")
    ap.add_argument("--data-dir", default=_DEFAULT_DATA_DIR,
                    help=f"数据目录（默认 {_DEFAULT_DATA_DIR}；测试隔离用）")
    args = ap.parse_args()

    dlq_path = os.path.join(args.data_dir, ".dead_letter_queue.jsonl")
    bus_path = os.path.join(args.data_dir, "event_bus.jsonl")
    processed_path = os.path.join(args.data_dir, "processed_ids.jsonl")

    entries = load_dlq(dlq_path)
    if not entries:
        print("[replay] 死信队列为空，无需重放")
        return 0

    unique, dropped = dedupe_by_event_id(entries)
    print(f"[replay] DLQ 明细行 {len(entries)} 条，去重后唯一事件 {len(unique)} 条"
          f"（合并同事件双记录 {dropped} 条）")

    if args.dry_run:
        list_entries(unique)
        print(f"\n[dry-run] ✅ 工具工作正常：{len(unique)} 条唯一死信待重放。"
              f"未注入任何事件、未修改 processed_ids。")
        return 0

    # ---- 真实重放 ----
    replay_ids = {e["event"].get("event_id") for e in unique if e["event"].get("event_id")}

    if replay_ids and not args.keep_processed:
        bak = backup_processed(processed_path)
        pruned = prune_processed(processed_path, replay_ids)
        print(f"[replay] 🗂️ processed_ids 剪除 {pruned} 条 event_id"
              + (f"（备份: {bak}）" if bak else ""))
        if pruned == 0:
            print("[replay] ⚠️ 注意: processed_ids 中未找到这些 event_id（可能已被压缩），直接注入")
    else:
        print("[replay] 🗂️ 跳过 processed_ids 剪除"
              + ("（--keep-processed）" if args.keep_processed else "（无 event_id 可剪）"))

    ok, failed = inject_events(bus_path, [e["event"] for e in unique])
    print("-" * 78)
    print(f"[replay] ✅ 已重放 {ok} 条（失败 {failed} 条），事件已写入 {bus_path}")
    print("[replay] 可在 operation_log.jsonl 观察消费结果（consumer 3s 轮询）；")
    print("[replay] 保留原 event_id —— 成功处理后仍按原键幂等去重，重复投递不会二次执行。")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
