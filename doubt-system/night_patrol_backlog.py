#!/usr/bin/env python3
"""night_patrol_backlog.py — 质疑闭环桥（2026-08-13 dandan 拍板）
把夜巡 findings 中的高价值警讯（severity>=4 且 confidence>=0.7）转成
backlog.md 待办（`- [ ] [质疑] <topic>: <suggestion>`），供每日巡检/
self_pulse 消费。去重：同 topic 同日期已有条目则跳过。只加不删，fail-open。

用法: python3 night_patrol_backlog.py --input /tmp/night_patrol_findings.json
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

BACKLOG = os.environ.get(
    "BACKLOG_FILE",
    "/vol1/@apphome/trim.openclaw/data/workspace/memory/backlog.md",
)
MIN_SEVERITY = 4
MIN_CONFIDENCE = 0.7
MAX_LEN = 100


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/tmp/night_patrol_findings.json")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        print("no findings file, skip")
        return 0
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"findings 解析失败: {e}")
        return 0

    findings = data.get("findings", []) if isinstance(data, dict) else data
    if not isinstance(findings, list):
        print("findings 结构异常，跳过")
        return 0

    date = data.get("date", time.strftime("%Y-%m-%d")) if isinstance(data, dict) else time.strftime("%Y-%m-%d")

    bp = Path(BACKLOG)
    try:
        bp.parent.mkdir(parents=True, exist_ok=True)
        existing = bp.read_text(encoding="utf-8") if bp.exists() else ""
    except Exception:
        existing = ""

    added = 0
    for it in findings:
        if not isinstance(it, dict):
            continue
        try:
            sev = int(it.get("severity", 0))
            conf = float(it.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        if sev < MIN_SEVERITY or conf < MIN_CONFIDENCE:
            continue
        topic = str(it.get("topic") or "夜巡").strip()
        suggestion = str(it.get("suggestion") or it.get("evidence") or "").replace("\n", " ").strip()
        if not suggestion:
            continue
        line = f"- [ ] [质疑] {topic}: {suggestion[:MAX_LEN]}（夜巡 {date}）"
        if line.strip() in existing:
            continue
        try:
            with bp.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            existing += line
            added += 1
        except Exception:
            pass

    print(f"night_patrol_backlog: findings={len(findings)} 高价值={added} 已入 backlog")
    return 0


if __name__ == "__main__":
    sys.exit(main())
