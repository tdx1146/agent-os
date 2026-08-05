#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compact_ids.py — processed_ids.jsonl 压缩工具（Phase 5 / 事件图谱治理）

把幂等去重日志 data/processed_ids.jsonl 压缩为仅保留最近 N 天（默认 7 天）的
event_id 记录，控制文件无限增长。原子重写（临时文件 + fsync + os.replace），
与 consumer 的 atomic_rewrite 同语义；压缩前自动备份（有删减时）。

语义说明：
  - 每条记录形如 {"event_id": "...", "t": "2026-08-04T17:03:06+08:00"}
  - 保留条件：t 在 [now - age_days, now] 区间内；t 缺失/解析失败 → 保守保留
    （无法判断年龄的记录不删，避免误删活跃去重键）
  - 被压缩掉的 event_id 若再次投递会被 consumer 当作新事件重新处理
    （幂等去重是安全网不是数据源，7 天前的记录压缩掉符合运维预期）

用法:
    python3 src/compact_ids.py                # 保留最近 7 天
    python3 src/compact_ids.py --age-days 30  # 保留最近 30 天
    python3 src/compact_ids.py --dry-run      # 只统计不写入
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta

_BJT = timezone(timedelta(hours=8))
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PROCESSED = os.path.join(
    os.path.dirname(_HERE), "data", "processed_ids.jsonl"
)


def _parse_ts(value):
    """解析 ISO8601 时间戳（含 +08:00 偏移），失败返回 None"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        # fromisoformat 对 'Z' 结尾处理：python3.11+ 支持，手动兜底
        if isinstance(dt, datetime) and dt.tzinfo is None:
            dt = dt.replace(tzinfo=_BJT)
        return dt
    except (ValueError, TypeError):
        return None


def compact(processed_path: str, age_days: int, dry_run: bool = False):
    if not os.path.exists(processed_path):
        print(f"[compact] ⚠️ 文件不存在: {processed_path}")
        return 0, 0

    cutoff = datetime.now(_BJT) - timedelta(days=age_days)
    keep_lines = []
    removed = 0
    total = 0
    no_ts_kept = 0

    with open(processed_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                keep_lines.append(line + "\n")
                continue
            ts = _parse_ts(rec.get("t"))
            if ts is None:
                no_ts_kept += 1
                keep_lines.append(line + "\n")
                continue
            if ts < cutoff:
                removed += 1
                continue
            keep_lines.append(line + "\n")

    print(f"[compact] 总行数 {total} | 保留 {len(keep_lines)} | 移除 {removed}"
          f"（其中 {no_ts_kept} 条无时间戳已保守保留）")
    print(f"[compact] 保留窗口: 最近 {age_days} 天（截止 {cutoff.isoformat()}）")

    if dry_run or removed == 0:
        print("[compact] " + ("dry-run，未写入" if dry_run else "无删减，无需重写"))
        return removed, total

    ts = datetime.now(_BJT).strftime("%Y%m%d-%H%M%S")
    bak = f"{processed_path}.bak.{ts}"
    shutil.copy2(processed_path, bak)
    print(f"[compact] 🗂️ 已备份: {bak}")

    from log_writer import LogWriter
    writer = LogWriter(processed_path)
    writer.atomic_rewrite(keep_lines)
    print(f"[compact] ✅ 压缩完成: {processed_path}（{total} → {len(keep_lines)} 行）")
    return removed, total


def main():
    ap = argparse.ArgumentParser(
        description="压缩 processed_ids.jsonl：仅保留最近 N 天 event_id（原子重写 + 自动备份）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--age-days", type=int, default=7,
                    help="保留天数（默认 7）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只统计不写入")
    ap.add_argument("--file", default=_DEFAULT_PROCESSED,
                    help=f"目标文件（默认 {_DEFAULT_PROCESSED}；测试隔离用）")
    args = ap.parse_args()

    if args.age_days < 1:
        print("[compact] ❌ --age-days 必须 ≥ 1")
        return 2

    removed, total = compact(args.file, args.age_days, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
