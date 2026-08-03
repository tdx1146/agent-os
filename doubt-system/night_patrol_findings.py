#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夜巡发现持久化器（自我怀疑系统 P2.3 回流）
============================================
把隔离子代理（夜巡·时间旁观者）产出的 findings（/tmp/night_patrol_findings.json）
按 observer schema 校验后回流：

  1. 校验：t / actor / form / tag / severity / confidence / evidence /
            topic / suggestion / status（缺失字段给默认值，越界值收敛）
  2. 指纹去重：扫描沙漏最近条目，同一 finding 不重复落沙（幂等，可重跑）
  3. 写沙漏：走官方 sandglass_log.log_message（带文件锁 + 影子索引），
     tag=旁观者-警讯（观察级）；不直写 SQLite（db 是 FTS 镜像，直写会被 sync 覆盖）
  4. 警讯级：severity>=4 且 confidence>=0.7 的条目追加到 /tmp/observer-alerts.json
     （flock 保护，供插件按主题匹配注入）
  5. 记录 operation_log（action=night_patrol_persist）

用法：
  python3 night_patrol_findings.py --input /tmp/night_patrol_findings.json
  python3 night_patrol_findings.py --self-test

环境变量：
  NEXSANDBASE_HOME  沙漏数据目录（默认 /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass）
"""

import argparse
import fcntl
import hashlib
import json
import os
import sys
from datetime import datetime

# ── 路径（与 night_patrol.py / lesson_capture.py 一致）─────────
_SOURCE_DIR = "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass_source"
_SANDBASE_HOME = os.environ.get(
    "NEXSANDBASE_HOME",
    "/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/sandglass",
)
# 关键：sandglass_log/sandglass_paths 读环境变量解析 _NB。
# 未显式设置时默认注入真实沙漏目录，防止写进 ~/.neurobase 空壳库。
os.environ.setdefault("NEXSANDBASE_HOME", _SANDBASE_HOME)
_SANDGLASS_TXT = os.path.join(_SANDBASE_HOME, "sandglass.txt")
_OP_LOG = "/vol1/@team/qh团队/QH/AI专用/Agent OS/iso-sand/data/operation_log.jsonl"
_ALERTS_FILE = "/tmp/observer-alerts.json"
_ALERTS_LOCK = "/tmp/observer-alerts.lock"
_DEDUPE_SCAN_LINES = 80

TAG = "旁观者-警讯"
FORM = "B"                      # 时间旁观者（夜巡）
STATUS_DEFAULT = "pending"
VALID_TAGS = {"旁观者洞察", "旁观者-警讯", "教训", "真值教训", "topic_risk"}
# 警讯级门槛（规划：L2 警讯级 = severity>=4 且 confidence>=0.7）
ALERT_SEVERITY_MIN = 4
ALERT_CONFIDENCE_MIN = 0.7


# ── 校验 / 归一 ────────────────────────────────────────────────

def norm_finding(f: dict, date: str) -> dict | None:
    """归一化一条 finding；结构非法返回 None（丢弃）。"""
    if not isinstance(f, dict):
        return None
    suggestion = str(f.get("suggestion") or "").strip()
    evidence = str(f.get("evidence") or "").strip()
    if not suggestion or not evidence:
        return None                       # 无建议或无证据 → 直接丢弃（证据强制铁律）
    try:
        severity = int(float(f.get("severity", 0)))
    except (TypeError, ValueError):
        severity = 0
    severity = max(1, min(5, severity))   # 1-5 收敛
    try:
        confidence = float(f.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))   # 0-1 收敛
    tag = str(f.get("tag") or TAG)
    if tag not in VALID_TAGS:
        tag = TAG
    return {
        "t": str(f.get("t") or datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")),
        "actor": str(f.get("actor") or f"observer-night-patrol-{date.replace('-', '')}"),
        "form": str(f.get("form") or FORM),
        "tag": tag,
        "severity": severity,
        "confidence": confidence,
        "evidence": evidence[:300],
        "topic": str(f.get("topic") or "未分类")[:60],
        "suggestion": suggestion[:300],
        "status": str(f.get("status") or STATUS_DEFAULT),
    }


def _fingerprint(f: dict) -> str:
    raw = (f["suggestion"][:50] + f["evidence"][:40]).strip()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _recent_lines(n: int = _DEDUPE_SCAN_LINES) -> list:
    """读沙漏最近 n 行（只读，不锁）。"""
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


# ── 写沙漏（官方接口，带锁）────────────────────────────────────

def write_to_sandglass(f: dict) -> bool:
    sys.path.insert(0, _SOURCE_DIR)
    try:
        from sandglass_log import log_message
        line = (
            f"【夜巡警讯】topic={f['topic']}；发现: {f['suggestion']}；"
            f"证据: {f['evidence']}；severity={f['severity']}/confidence={f['confidence']}；"
            f"actor={f['actor']} form={f['form']} status={f['status']}；tag={f['tag']}"
        )
        return bool(log_message(line, sender="agent"))
    except Exception as e:
        print(f"  [sandglass write failed] {e}", file=sys.stderr)
        return False


# ── 警讯级追加 /tmp/observer-alerts.json ───────────────────────

def append_alert(f: dict) -> bool:
    """把高价值 finding 追加到 observer-alerts.json（flock 保护，数组格式）。

    按指纹去重：同一条警讯不重复追加（插件注入会逐条消费，重复=噪音）。
    """
    fp = _fingerprint(f)
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
                return True          # 已存在，跳过（视为成功）
            existing.append(dict(f, written_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            with open(_ALERTS_FILE, "w", encoding="utf-8") as fh:
                json.dump(existing, fh, ensure_ascii=False, indent=2)
            fcntl.flock(lockf, fcntl.LOCK_UN)
        return True
    except Exception as e:
        print(f"  [observer-alerts append failed] {e}", file=sys.stderr)
        return False


# ── operation_log ──────────────────────────────────────────────

def log_op(level: str, action: str, result: str, detail: str) -> None:
    try:
        rec = {
            "t": datetime.now().isoformat(),
            "level": level,
            "actor": "night_patrol",
            "action": action,
            "target": "night_patrol",
            "result": result,
            "detail": detail,
        }
        with open(_OP_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── 主流程 ────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="夜巡发现持久化器")
    parser.add_argument("--input", default="/tmp/night_patrol_findings.json")
    parser.add_argument("--dry-run", action="store_true", help="只校验不写入")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not os.path.exists(args.input):
        print(json.dumps({"persisted": 0, "skipped": 0, "reason": "input_missing",
                          "input": args.input}, ensure_ascii=False))
        log_op("WARN", "night_patrol_persist", "SKIP", f"findings 文件不存在: {args.input}")
        return 0

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(json.dumps({"persisted": 0, "skipped": 0, "reason": f"parse_error: {e}"},
                         ensure_ascii=False))
        log_op("ERROR", "night_patrol_persist", "FAIL", f"findings 解析失败: {e}")
        return 1

    date = str(payload.get("date") or datetime.now().strftime("%Y-%m-%d"))
    raw_findings = payload.get("findings", [])
    if not isinstance(raw_findings, list):
        raw_findings = []

    findings = [nf for nf in (norm_finding(f, date) for f in raw_findings) if nf]

    # 指纹去重（幂等重跑）
    recent = _recent_lines()
    kept, deduped = [], 0
    for f in findings:
        fp = _fingerprint(f)
        hit = False
        for ln in recent:
            if fp in ln or (f["suggestion"][:30] in ln and f["evidence"][:20] in ln):
                hit = True
                break
        if hit:
            deduped += 1
            continue
        kept.append(f)

    if args.dry_run:
        print(json.dumps({"dry_run": True, "valid": len(findings),
                          "would_write": len(kept), "deduped": deduped}, ensure_ascii=False))
        return 0

    written, alerts = 0, 0
    for f in kept:
        if write_to_sandglass(f):
            written += 1
        if f["severity"] >= ALERT_SEVERITY_MIN and f["confidence"] >= ALERT_CONFIDENCE_MIN:
            if append_alert(f):
                alerts += 1

    summary = {"persisted": written, "deduped": deduped, "invalid": len(raw_findings) - len(findings),
               "alerts_appended": alerts, "date": date, "tag": TAG}
    print(json.dumps(summary, ensure_ascii=False))
    log_op("INFO", "night_patrol_persist", "OK" if written else "OK",
           f"date={date} findings={len(raw_findings)} valid={len(findings)} "
           f"written={written} deduped={deduped} alerts={alerts}")
    return 0


def self_test() -> int:
    print("夜巡发现持久化器自检")
    ok = True
    good = {
        "t": "2026-08-03T23:30:00+08:00",
        "actor": "observer-night-patrol-20260803",
        "form": "B",
        "tag": "旁观者-警讯",
        "severity": 4,
        "confidence": 0.8,
        "evidence": "sandglass#4210",
        "topic": "夜巡测试",
        "suggestion": "自检建议：检查 topic_risk 是否维护",
        "status": "pending",
    }
    nf = norm_finding(good, "2026-08-03")
    ok &= nf is not None and nf["severity"] == 4 and nf["confidence"] == 0.8
    print(f"  ✅ 合法 finding 归一: severity={nf['severity']} confidence={nf['confidence']}")

    # 越界收敛
    bad_range = dict(good, severity=9, confidence=2.0)
    nf2 = norm_finding(bad_range, "2026-08-03")
    ok &= nf2["severity"] == 5 and nf2["confidence"] == 1.0
    print(f"  ✅ 越界收敛: severity 9→{nf2['severity']}, confidence 2.0→{nf2['confidence']}")

    # 无证据丢弃
    no_evidence = dict(good, evidence="")
    ok &= norm_finding(no_evidence, "2026-08-03") is None
    print("  ✅ 无证据丢弃")

    # 非法 tag 回退
    bad_tag = dict(good, tag="不存在的tag")
    nf3 = norm_finding(bad_tag, "2026-08-03")
    ok &= nf3["tag"] == TAG
    print(f"  ✅ 非法 tag 回退: → {nf3['tag']}")

    # 指纹稳定
    ok &= _fingerprint(nf) == _fingerprint(norm_finding(good, "2026-08-03"))
    print("  ✅ 指纹稳定")

    print(f"\n自检 {'通过' if ok else '失败'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
