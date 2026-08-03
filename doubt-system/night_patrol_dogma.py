#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反教条复核器（自我怀疑系统 P3.3 / L4 增强夜巡）
================================================
理念：定期挑出被引用最多的记忆/教训，注入"这些记忆可能已过时"的复核提示，
让新信息有机会推翻旧结论——防止高频引用把旧结论固化成教条（防回声室）。

流程：
  1. 候选记忆 = doubt.db 的 memory_trust 表（P3.2 建表后优先，按 reference_count 排序）
     或降级：从沙漏"注入痕迹"推断（【教训】/tag=lesson/真值教训/【记忆】/权威断言/【夜巡警讯】）
  2. 取 top10（reference_count 降序）→ 复核项 {memory_id, ts, text_preview, reference_count, reason}
  3. 低频写沙漏（默认每天最多 3 条，tag=旁观者-警讯，severity 2-3）
     + 追加 /tmp/observer-alerts.json（插件侧按 topic 匹配注入）
  4. 年龄门槛：默认只复核 >=30 天前的高频记忆 → reason="被高频引用超过30天"
  5. 幂等：指纹去重（沙漏最近条目 + 当日状态文件），可重跑

原则（规划第五部分）：
  - 只写"复核信号"，不写结论（防回声室）：confidence 固定 0.5-0.6，severity 2-3
  - 低频：每天最多 MAX_PER_DAY 条（默认3），不做背景音乐
  - 带证据：每条必须含 memory_id
  - 不直写 SQLite：写沙漏走官方 sandglass_log.log_message（文件锁+影子索引）

用法：
  python3 night_patrol_dogma.py                    # 常规运行（写沙漏，≤3条/天）
  python3 night_patrol_dogma.py --list             # 只输出 top10 复核项 JSON（不写任何东西）
  python3 night_patrol_dogma.py --dry-run          # 校验+预览将写入的条目（不写）
  python3 night_patrol_dogma.py --min-age-days 0   # 测试：忽略年龄门槛
  python3 night_patrol_dogma.py --self-test

环境变量：
  NEXSANDBASE_HOME   沙漏数据目录（默认 /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass）
  DOGMA_MAX_PER_DAY  每日写入上限（默认 3）
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta

# ── 路径（与 night_patrol_findings.py / lesson_capture.py 一致）─────────
_SOURCE_DIR = "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass_source"
_SANDBASE_HOME = os.environ.get(
    "NEXSANDBASE_HOME",
    "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass",
)
os.environ.setdefault("NEXSANDBASE_HOME", _SANDBASE_HOME)
_SANDGLASS_TXT = os.path.join(_SANDBASE_HOME, "sandglass.txt")
_SANDBASE_DB = os.path.join(_SANDBASE_HOME, "sandglass.db")   # FTS5 镜像（只读，用于解析 memory_id）
_DOUBT_DB = os.path.join(_SANDBASE_HOME, "doubt.db")
_OP_LOG = "/vol1/@team/qh团队/QH/AI专用/Agent OS/iso-sand/data/operation_log.jsonl"
_ALERTS_FILE = "/tmp/observer-alerts.json"
_ALERTS_LOCK = "/tmp/observer-alerts.lock"
_STATE_FILE = "/vol1/@apphome/trim.openclaw/data/workspace/logs/dogma_state.json"

TAG = "旁观者-警讯"
FORM = "D"                      # 反教条旁观者（新旁观者形态）
TOP_N = 10                      # top10 复核项
MIN_AGE_DAYS = 30               # 默认年龄门槛：只复核 >=30 天前的高频记忆
MAX_PER_DAY = int(os.environ.get("DOGMA_MAX_PER_DAY", "3"))
_DEDUPE_SCAN_LINES = 80
_PREVIEW_MAX = 120              # text_preview 截断
_REASON_AGED = "被高频引用超过30天"

# 注入痕迹标记（沙漏中"结论类"条目 = 会被当作记忆引用的注入）
_MARKERS = [
    "【教训】", "【记忆】", "tag=lesson", "真值教训", "tag=教训",
    "权威断言", "【夜巡警讯】",
]
# 通用词拦截（避免把"用户纠错""原始判断"这类固定前缀当主题 token）
_STOP_TOKENS = [
    "用户纠错", "差距分析", "原始判断", "被纠正为", "需要", "建议", "检查",
    "注意", "未分类", "topic_risk", "发现", "证据", "后续动作", "根因",
]


# ═══════════════════ 候选记忆采集 ═══════════════════

def _parse_sandglass():
    """解析 sandglass.txt → (raw_lines, entries)。

    entries: [(lineno, ts, sender, text)]，仅标准行
    （沙漏多行消息只有首行带时间戳前缀，续行跳过——它们没有 ts 无法算年龄）。
    """
    if not os.path.exists(_SANDGLASS_TXT):
        return [], []
    with open(_SANDGLASS_TXT, "r", encoding="utf-8", errors="replace") as f:
        raw_lines = f.read().splitlines()
    entries = []
    for i, ln in enumerate(raw_lines, 1):
        m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\S+) \| (.*)$", ln)
        if m:
            entries.append((i, m.group(1), m.group(2), m.group(3)))
    return raw_lines, entries


def _load_mirror_ids():
    """sandglass.db 镜像 → {(ts, sender, text[:50]): id}，用于把 txt 行解析成 memory_id。"""
    out = {}
    if not os.path.exists(_SANDBASE_DB):
        return out
    try:
        conn = sqlite3.connect(f"file:{_SANDBASE_DB}?mode=ro", uri=True)
        for r in conn.execute("SELECT id, ts, sender, text FROM sandglass").fetchall():
            out.setdefault((r[1], r[2], (r[3] or "")[:50]), r[0])
        conn.close()
    except Exception:
        pass
    return out


def _extract_token(text: str) -> str | None:
    """从注入痕迹提取"主题 token"（用于统计被引用次数）。"""
    m = re.search(r"topic=([^\s；;，,]+)", text)
    if m:
        return m.group(1)[:20]
    for pat in (r"原始判断[:：]\s*([^；;，,。]+)", r"被纠正为[:：]\s*([^；;，,。]+)"):
        m2 = re.search(pat, text)
        if m2:
            return m2.group(1).strip()[:24]
    m4 = re.search(r"(【教训】|【记忆】|真值教训|权威断言|【夜巡警讯】)", text)
    after = text[m4.end():] if m4 else text
    clause = re.split(r"[；;，,。！？]", after)[0].strip()
    clause = re.sub(r"^发现[:：]\s*", "", clause)
    return clause[:24]


def _count_refs(token: str, raw_lines: list, self_lineno: int) -> int:
    """引用次数：其他行包含该 token 的行数。

    启发式：完整 token 命中优先；若 0 命中且 token 较长，回退用前 8 字符
    （更可能被后续条目以口语形式引用）。启发式仅用于排序，非精确统计。
    """
    if not token:
        return 0
    cnt = sum(1 for j, ln in enumerate(raw_lines, 1) if j != self_lineno and token in ln)
    if cnt == 0 and len(token) > 8:
        cnt = sum(1 for j, ln in enumerate(raw_lines, 1) if j != self_lineno and token[:8] in ln)
    return cnt


def load_memory_trust() -> list | None:
    """doubt.db memory_trust 表（P3.2 记忆信任度）。表不存在/结构不符 → None（走注入痕迹降级）。"""
    if not os.path.exists(_DOUBT_DB):
        return None
    try:
        conn = sqlite3.connect(f"file:{_DOUBT_DB}?mode=ro", uri=True)
        cur = conn.cursor()
        cols = [c[1] for c in cur.execute("PRAGMA table_info(memory_trust)").fetchall()]
        if "memory_trust" not in [c[0] for c in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
            conn.close()
            return None
        need = {"memory_id", "reference_count"}
        if not need.issubset(set(cols)):
            conn.close()
            return None
        rows = cur.execute(
            "SELECT memory_id, ts, text_preview, reference_count FROM memory_trust "
            "ORDER BY reference_count DESC LIMIT ?", (TOP_N,)
        ).fetchall()
        conn.close()
        out = []
        for r in rows:
            out.append({
                "memory_id": str(r[0]),
                "ts": _norm_ts(r[1]),
                "text_preview": str(r[2] or "")[:_PREVIEW_MAX],
                "reference_count": int(r[3] or 0),
            })
        return out if out else None
    except Exception:
        return None


def _norm_ts(ts) -> str:
    """把 memory_trust 的 ts（unix 数值或字符串）归一为 'YYYY-MM-DD HH:MM:SS'。"""
    if ts is None:
        return ""
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError):
            return str(ts)
    s = str(ts).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return s


def infer_candidates() -> list:
    """降级：从沙漏注入痕迹推断候选记忆。返回按 reference_count 降序的列表。"""
    raw_lines, entries = _parse_sandglass()
    if not entries:
        return []
    mirror = _load_mirror_ids()
    cands = []
    for (lineno, ts, sender, text) in entries:
        if "【反教条复核】" in text:          # 排除自身输出，防反馈回路
            continue
        if not any(mk in text for mk in _MARKERS):
            continue
        tok = _extract_token(text)
        if not tok or len(tok) < 4:
            continue
        if any(s in tok for s in _STOP_TOKENS):
            continue
        mid = mirror.get((ts, sender, text[:50]), f"txt#{lineno}")
        cands.append({
            "memory_id": str(mid),
            "ts": ts,
            "text_preview": text[:_PREVIEW_MAX],
            "reference_count": _count_refs(tok, raw_lines, lineno),
            "_token": tok,
        })
    cands.sort(key=lambda c: (-c["reference_count"], c["ts"]))
    return cands


def build_review_items(candidates: list, min_age_days: int) -> list:
    """top10 → 复核项 {memory_id, ts, text_preview, reference_count, reason, age_days, severity}。"""
    now = datetime.now()
    items = []
    for c in candidates[:TOP_N]:
        age_days = None
        try:
            t = datetime.strptime(c["ts"][:19], "%Y-%m-%d %H:%M:%S")
            age_days = (now - t).days
        except (ValueError, TypeError):
            age_days = 0
        aged = age_days >= min_age_days
        items.append({
            "memory_id": c["memory_id"],
            "ts": c["ts"],
            "text_preview": c["text_preview"],
            "reference_count": c["reference_count"],
            "reason": _REASON_AGED if aged else f"被高频引用但仅{age_days}天（未达{min_age_days}天复核线）",
            "age_days": age_days,
            "severity": 3 if aged else 2,          # 复核信号：2-3，不做高分警讯
            "topic": c.get("_token", "记忆复核")[:20],
        })
    return items


# ═══════════════════ 幂等 / 状态 ═══════════════════

def _fingerprint(item: dict) -> str:
    """指纹需容忍外部条目（如 night_patrol 的警讯）缺 memory_id/text_preview 字段。"""
    mid = str(item.get("memory_id") or "")
    preview = str(item.get("text_preview") or "")[:40]
    raw = (mid + preview).strip()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _recent_lines(n: int = _DEDUPE_SCAN_LINES) -> list:
    if not os.path.exists(_SANDGLASS_TXT):
        return []
    try:
        with open(_SANDGLASS_TXT, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = max(8192, size)
            f.seek(max(0, size - chunk))
            data = f.read().decode("utf-8", errors="ignore")
        return [ln for ln in data.splitlines() if ln.strip()][-n:]
    except Exception:
        return []


def _load_state() -> dict:
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
        return st if isinstance(st, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(st: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def select_for_write(items: list, max_per_day: int, min_age_days: int, dry_run: bool = False) -> dict:
    """年龄门槛 + 当日限额 + 指纹去重 → 本次实际要写的条目。"""
    today = datetime.now().strftime("%Y-%m-%d")
    state = _load_state()
    if state.get("date") != today:
        state = {"date": today, "written": [], "count": 0}
    recent = _recent_lines()

    # 年龄门槛：只复核 >= min_age_days 天前的高频记忆（默认30天）——
    # 新鲜记忆不注入"可能已过时"，避免背景音乐噪音（怀疑是消防队不是背景音乐）
    eligible = [it for it in items if it["age_days"] >= min_age_days]
    age_skipped = [{"memory_id": it["memory_id"], "reason": "below_age_gate",
                    "age_days": it["age_days"]}
                   for it in items if it["age_days"] < min_age_days]
    chosen, skipped = [], list(age_skipped)
    for it in eligible:
        if len(chosen) >= max_per_day - state.get("count", 0):
            skipped.append({"memory_id": it["memory_id"], "reason": "rate_limit"})
            continue
        fp = _fingerprint(it)
        if fp in state.get("written", []):
            skipped.append({"memory_id": it["memory_id"], "reason": "state_dedupe"})
            continue
        hit = any(fp in ln or (it["text_preview"][:20] in ln and f"memory_id={it['memory_id']}" in ln)
                  for ln in recent)
        if hit:
            skipped.append({"memory_id": it["memory_id"], "reason": "sandglass_dedupe"})
            continue
        chosen.append(it)

    if not dry_run and chosen:
        state["written"] = state.get("written", []) + [_fingerprint(it) for it in chosen]
        state["count"] = state.get("count", 0) + len(chosen)
        state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _save_state(state)
    return {"chosen": chosen, "skipped": skipped, "state": state}


# ═══════════════════ 写沙漏 + 警讯文件 ═══════════════════

def write_item(item: dict) -> bool:
    line = (
        f"【反教条复核】topic={item['topic']}；发现: 记忆可能已过时：{item['text_preview']}；"
        f"证据: memory_id={item['memory_id']} reference_count={item['reference_count']} ts={item['ts']}；"
        f"reason: {item['reason']}；severity={item['severity']}/confidence=0.55；"
        f"actor=observer-dogma-{datetime.now().strftime('%Y%m%d')} form={FORM} status=pending；tag={TAG}"
    )
    sys.path.insert(0, _SOURCE_DIR)
    try:
        from sandglass_log import log_message
        return bool(log_message(line, sender="agent"))
    except Exception as e:
        print(f"  [sandglass write failed] {e}", file=sys.stderr)
        return False


def append_alert(item: dict) -> bool:
    """追加 /tmp/observer-alerts.json（与 night_patrol_findings 同锁同格式，插件按 topic 匹配注入）。

    反教条条目 severity 2-3 也写入——它们属于"复核类"警讯，用 kind=dogma-review 标记，
    供插件侧与 severity>=4 的硬警讯区分处理。
    """
    fp = _fingerprint(item)
    alert = {
        "t": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "actor": f"observer-dogma-{datetime.now().strftime('%Y%m%d')}",
        "form": FORM,
        "tag": TAG,
        "kind": "dogma-review",                 # 复核类标记（插件侧可按此分类）
        "severity": item["severity"],
        "confidence": 0.55,
        "evidence": f"memory_id={item['memory_id']} reference_count={item['reference_count']} ts={item['ts']}",
        "topic": item["topic"],
        "suggestion": f"复核记忆是否仍适用：{item['text_preview'][:150]}（reason: {item['reason']}）",
        "status": "pending",
    }
    try:
        with open(_ALERTS_LOCK, "w") as lockf:
            fcntl.flock(lockf, fcntl.LOCK_EX)
            existing = []
            if os.path.exists(_ALERTS_FILE):
                try:
                    with open(_ALERTS_FILE, "r", encoding="utf-8") as fh:
                        existing = json.load(fh)
                    if not isinstance(existing, list):
                        existing = []
                except (json.JSONDecodeError, OSError):
                    existing = []
            if any(_fingerprint(e) == fp for e in existing if isinstance(e, dict)):
                fcntl.flock(lockf, fcntl.LOCK_UN)
                return True
            existing.append(dict(alert, written_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            with open(_ALERTS_FILE, "w", encoding="utf-8") as fh:
                json.dump(existing, fh, ensure_ascii=False, indent=2)
            fcntl.flock(lockf, fcntl.LOCK_UN)
        return True
    except Exception as e:
        print(f"  [observer-alerts append failed] {e}", file=sys.stderr)
        return False


def log_op(level: str, action: str, result: str, detail: str) -> None:
    try:
        rec = {
            "t": datetime.now().isoformat(),
            "level": level,
            "actor": "night_patrol_dogma",
            "action": action,
            "target": "night_patrol",
            "result": result,
            "detail": detail,
        }
        with open(_OP_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ═══════════════════ 主流程 ═══════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="反教条复核器（P3.3）")
    parser.add_argument("--list", action="store_true", help="只输出 top10 复核项 JSON，不写任何东西")
    parser.add_argument("--dry-run", action="store_true", help="预览将写入的条目，不写")
    parser.add_argument("--min-age-days", type=int, default=MIN_AGE_DAYS,
                        help=f"年龄门槛（默认 {MIN_AGE_DAYS} 天；0 = 测试模式不过滤）")
    parser.add_argument("--max-per-day", type=int, default=MAX_PER_DAY, help="每日写入上限")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    # 1. 候选：memory_trust 优先，降级注入痕迹
    from_trust = load_memory_trust()
    source = "memory_trust" if from_trust else "injection_trace"
    candidates = from_trust if from_trust else infer_candidates()

    # 2. top10 复核项
    items = build_review_items(candidates, args.min_age_days)

    if args.list:
        out = {
            "source": source,
            "min_age_days": args.min_age_days,
            "candidate_total": len(candidates),
            "items": [{k: v for k, v in it.items() if k != "topic"} for it in items],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # 3. 选写（年龄 + 限额 + 去重）
    sel = select_for_write(items, args.max_per_day, args.min_age_days, dry_run=args.dry_run)

    if args.dry_run:
        print(json.dumps({
            "dry_run": True, "source": source, "candidates": len(candidates),
            "would_write": len(sel["chosen"]), "skipped": sel["skipped"],
            "items": [{k: v for k, v in it.items() if k != "topic"} for it in sel["chosen"]],
        }, ensure_ascii=False, indent=2))
        return 0

    # 4. 写沙漏 + 警讯文件
    written = 0
    for it in sel["chosen"]:
        if write_item(it):
            written += 1
        append_alert(it)

    summary = {
        "source": source,
        "candidates": len(candidates),
        "top_items": len(items),
        "written": written,
        "skipped": sel["skipped"],
        "today_count": sel["state"].get("count", 0),
        "max_per_day": args.max_per_day,
        "min_age_days": args.min_age_days,
    }
    print(json.dumps(summary, ensure_ascii=False))
    log_op("INFO", "dogma_review", "OK" if written else "OK",
           f"source={source} candidates={len(candidates)} written={written} "
           f"skipped={len(sel['skipped'])} today_count={sel['state'].get('count', 0)}")
    return 0


def self_test() -> int:
    print("反教条复核器自检")
    ok = True

    # 1. token 提取
    t1 = _extract_token("【夜巡警讯】topic=沙漏同步；发现: 检查 sync 幂等性")
    ok &= t1 == "沙漏同步"
    print(f"  ✅ topic= 提取: {t1!r}")
    t2 = _extract_token("【教训】用户纠错 → 原始判断: 端口是19999；被纠正为: 端口是18888；差距分析: ...")
    ok &= t2 == "端口是19999"
    print(f"  ✅ 原始判断提取: {t2!r}")
    t3 = _extract_token("【记忆】v5.0 编辑器在 /vol1 目录下运行正常。")
    ok &= t3 and "v5.0" in t3
    print(f"  ✅ 记忆首句提取: {t3!r}")

    # 2. 引用计数
    raw = ["2026-01-01 00:00:00 | agent | 【教训】端口是19999 是错的",
           "2026-01-02 00:00:00 | agent | 端口是19999 应该改成 18888",
           "2026-01-03 00:00:00 | agent | 确认端口 18888 正确"]
    cnt = _count_refs("端口是19999", raw, 1)
    ok &= cnt == 1
    print(f"  ✅ 引用计数: {cnt}（应=1）")

    # 3. 复核项构建（年龄门槛）
    items = build_review_items([
        {"memory_id": "m1", "ts": (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S"),
         "text_preview": "旧教训A", "reference_count": 9, "_token": "tokA"},
        {"memory_id": "m2", "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "text_preview": "新教训B", "reference_count": 10, "_token": "tokB"},
    ], min_age_days=30)
    ok &= len(items) == 2
    ok &= items[0]["reason"] == _REASON_AGED and items[0]["severity"] == 3
    ok &= items[1]["severity"] == 2 and "未达" in items[1]["reason"]
    print(f"  ✅ 年龄门槛: 40天→reason={items[0]['reason']!r} severity={items[0]['severity']}；"
          f"0天→severity={items[1]['severity']}")

    # 4. 指纹稳定
    fp = _fingerprint({"memory_id": "m1", "text_preview": "旧教训A"})
    ok &= fp == _fingerprint({"memory_id": "m1", "text_preview": "旧教训A"})
    print(f"  ✅ 指纹稳定: {fp}")

    # 5. 真实数据降级采集（不写库，只验证管道不炸）
    cands = infer_candidates()
    print(f"  ✅ 注入痕迹降级采集: {len(cands)} 条候选（真实数据）")
    if cands:
        top = cands[0]
        ok &= all(k in top for k in ("memory_id", "ts", "text_preview", "reference_count"))
        print(f"     top1: id={top['memory_id']} refs={top['reference_count']} ts={top['ts']}")

    print(f"\n自检 {'通过' if ok else '失败'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
