#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夜巡数据汇总器（自我怀疑系统 P2.3 / L4 时间旁观者）
====================================================
汇总"当天"数据到 /tmp/night_patrol_input.json，供隔离子代理（夜巡·时间旁观者）
在 23:30 用独立上下文回看当天，找矛盾 / 模式 / 被忽略的教训。

数据源（全部只读）：
  1. 沙漏 sandglass.db        —— 当天 ts 的对话记录（SQLite FTS5 镜像，URI mode=ro）
  2. workspace/memory/*.md    —— 当天文件（文件名含日期 或 mtime 当天）
  3. operation_log.jsonl      —— 当天的 FAIL 行（result=FAIL 或 level=ERROR）
  4. doubt.db doubt_episode   —— 当天的怀疑账本记录（P1.2）
  5. /tmp/topic_risk.json     —— 若存在（P2.4 数据，先汇总）

原则（对应规划第五部分）：
  - 幂等可重跑：每次覆盖输出文件，无状态，不写任何数据源
  - 不调 LLM：纯数据准备，LLM 分析由 cron 的隔离子代理接手
  - SQLite 以只读模式打开（?mode=ro），绝不写库
  - 旁观者看原文：dialogue 保留当天对话原文（截断），dialogue_summary 只做计数摘要

用法：
  python3 night_patrol.py                    # 汇总今天
  python3 night_patrol.py --date 2026-08-03  # 指定日期（回测）
  python3 night_patrol.py --output /tmp/x.json

环境变量：
  NEXSANDBASE_HOME  沙漏数据目录（默认 /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass）
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

# ── 路径（绝对化，规划文件清单）────────────────────────────────
SANDBASE_HOME = os.environ.get(
    "NEXSANDBASE_HOME",
    "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass",
)
SANDBASE_DB = os.path.join(SANDBASE_HOME, "sandglass.db")
DOUBT_DB = os.path.join(SANDBASE_HOME, "doubt.db")
OP_LOG = "/vol1/@team/qh团队/QH/AI专用/Agent OS/iso-sand/data/operation_log.jsonl"
MEMORY_DIR = "/vol1/@apphome/trim.openclaw/data/workspace/memory"
RISK_FILE = "/tmp/topic_risk.json"
OUTPUT = "/tmp/night_patrol_input.json"

# 截断上限（控制输入体积，LLM 可读性）
DIALOGUE_MAX = 800          # 最多保留的对话条目
TEXT_MAX = 400              # 单条文本截断
DETAIL_MAX = 300            # operation_log detail 截断
MEM_PREVIEW_MAX = 200       # memory 文件预览


def parse_date_arg() -> str:
    """解析 --date YYYY-MM-DD，默认今天（本地时区）。"""
    args = sys.argv[1:]
    if "--date" in args:
        i = args.index("--date")
        if i + 1 < len(args):
            return args[i + 1]
    return datetime.now().strftime("%Y-%m-%d")


def parse_output_arg() -> str:
    args = sys.argv[1:]
    if "--output" in args:
        i = args.index("--output")
        if i + 1 < len(args):
            return args[i + 1]
    return OUTPUT


# ── 数据源采集 ────────────────────────────────────────────────

def read_sandglass(d: str) -> dict:
    """当天沙漏对话（SQLite 只读）。返回 (rows, sources_status)。"""
    start = f"{d} 00:00:00"
    end = (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    try:
        conn = sqlite3.connect(f"file:{SANDBASE_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, ts, sender, text FROM sandglass WHERE ts >= ? AND ts < ? ORDER BY ts, id",
            (start, end),
        ).fetchall()
        conn.close()
        out = []
        seen = set()
        for r in rows:
            text = (r["text"] or "")[:TEXT_MAX]
            key = (r["ts"], r["sender"], text)
            if key in seen:          # db 是 txt 的 FTS 镜像，可能有重复行
                continue
            seen.add(key)
            out.append({"id": r["id"], "ts": r["ts"], "sender": r["sender"], "text": text})
        out = out[-DIALOGUE_MAX:]
        return out, "ok"
    except Exception as e:
        return [], f"error: {e}"


def summarize_dialogue(rows: list) -> dict:
    """对话摘要：计数 + 起止时间 + 按 sender 分布。"""
    by_sender: dict = {}
    for r in rows:
        by_sender[r["sender"]] = by_sender.get(r["sender"], 0) + 1
    first = rows[0]["ts"] if rows else None
    last = rows[-1]["ts"] if rows else None
    return {
        "total": len(rows),
        "by_sender": by_sender,
        "span": {"first": first, "last": last},
        "note": "dialogue 为当天原文（截断后），供旁观者读原文；本字段仅计数摘要",
    }


def read_fails(d: str) -> list:
    """operation_log 当天 FAIL 行（result=FAIL 或 level=ERROR）。"""
    fails = []
    if not os.path.exists(OP_LOG):
        return fails
    try:
        with open(OP_LOG, "r", encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line or d not in line[:40]:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = rec.get("t") or rec.get("timestamp") or ""
                if not str(ts).startswith(d):
                    continue
                if rec.get("result") == "FAIL" or rec.get("level") == "ERROR":
                    detail = str(rec.get("detail") or "")[:DETAIL_MAX]
                    fails.append({
                        "line": lineno,
                        "t": ts,
                        "level": rec.get("level"),
                        "actor": rec.get("actor"),
                        "action": rec.get("action"),
                        "result": rec.get("result"),
                        "detail": detail,
                    })
    except Exception:
        pass
    return fails


def read_doubts(d: str) -> list:
    """doubt_episode 当天记录（t 为 unix 时间戳，本地时区）。"""
    doubts = []
    if not os.path.exists(DOUBT_DB):
        return doubts
    try:
        conn = sqlite3.connect(f"file:{DOUBT_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT * FROM doubt_episode ORDER BY t"
        ).fetchall()
        conn.close()
        day_start = datetime.strptime(d, "%Y-%m-%d")
        day_end = day_start + timedelta(days=1)
        for r in rows:
            try:
                ts = datetime.fromtimestamp(float(r["t"]))
            except (TypeError, ValueError, OSError):
                continue
            if day_start <= ts < day_end:
                doubts.append({
                    "id": r["id"],
                    "t": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "trigger_type": r["trigger_type"],
                    "suspicion": (r["suspicion"] or "")[:TEXT_MAX],
                    "queried": r["queried"],
                    "answer_changed": r["answer_changed"],
                    "overturn_evidence": (r["overturn_evidence"] or "")[:TEXT_MAX],
                    "user_reaction": r["user_reaction"],
                    "topic": r["topic"],
                    "confidence_after": r["confidence_after"],
                })
    except Exception:
        pass
    return doubts


def read_memory_files(d: str) -> list:
    """workspace/memory/ 当天文件：文件名含日期 或 mtime 当天。"""
    out = []
    if not os.path.isdir(MEMORY_DIR):
        return out
    try:
        for name in sorted(os.listdir(MEMORY_DIR)):
            if name.startswith(".") or name.endswith((".pyc",)):
                continue
            path = os.path.join(MEMORY_DIR, name)
            if not os.path.isfile(path):
                continue
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            name_has_date = d in name
            mtime_today = mtime.strftime("%Y-%m-%d") == d
            if not (name_has_date or mtime_today):
                continue
            preview = ""
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    preview = f.read(MEM_PREVIEW_MAX).replace("\n", " ")
            except Exception:
                pass
            out.append({
                "name": name,
                "mtime": mtime.strftime("%Y-%m-%d %H:%M:%S"),
                "size": os.path.getsize(path),
                "preview": preview,
            })
    except Exception:
        pass
    return out


def read_risks() -> dict | None:
    """/tmp/topic_risk.json 若存在。"""
    if not os.path.exists(RISK_FILE):
        return None
    try:
        with open(RISK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"raw": data}
    except Exception as e:
        return {"error": str(e)}


# ── 主流程 ────────────────────────────────────────────────────

def main() -> int:
    d = parse_date_arg()
    output = parse_output_arg()

    dialogue, sg_status = read_sandglass(d)
    payload = {
        "date": d,
        "dialogue": dialogue,
        "dialogue_summary": summarize_dialogue(dialogue),
        "fails": read_fails(d),
        "doubts": read_doubts(d),
        "risks": read_risks(),
        "memory_files": read_memory_files(d),
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sources": {
                "sandglass_db": sg_status,
                "operation_log": "ok" if os.path.exists(OP_LOG) else "missing",
                "doubt_db": "ok" if os.path.exists(DOUBT_DB) else "missing",
                "memory_dir": "ok" if os.path.isdir(MEMORY_DIR) else "missing",
                "topic_risk": "present" if os.path.exists(RISK_FILE) else "absent",
            },
        },
    }

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "output": output,
        "date": d,
        "dialogue_entries": len(dialogue),
        "fails": len(payload["fails"]),
        "doubts": len(payload["doubts"]),
        "memory_files": len(payload["memory_files"]),
        "topic_risk": "present" if payload["risks"] else "absent",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
