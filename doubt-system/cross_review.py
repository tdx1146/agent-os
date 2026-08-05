#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨实例互审（自我怀疑系统 P3.3）
================================
理念：用 jiali 通道让妹妹的系统当旁观者——把关键决策摘要（脱敏）发给
jiali.tdx1146.com:18888/api/inject，妹妹系统审查后回传意见，写入沙漏
（tag=旁观者-洞察，actor=cross-instance）。

流程：
  1. build_summary: 决策主题 + 2-3 选项 + 我的倾向（脱敏：不含敏感路径/密钥）
  2. send: POST http://jiali.tdx1146.com:18888/api/inject
           body {"message": "[姐姐→妹妹] 跨实例互审请求: ..."}
     （格式参照现有 /api/inject：注入消息到对端当前会话）
  3. scan: 扫描沙漏最近 1 小时 sender∈{sister,user} 且含"互审"的行 → 提取意见
  4. persist: 意见写沙漏 tag=旁观者-洞察 actor=cross-instance form=C
  5. 失败静默：妹妹机器时段性不可达是常态，不阻塞、不告警（只记 operation_log）

默认 DISABLED：需环境变量 CROSS_REVIEW=1 才真正发送（妹妹机器时段性不可达）。
夜巡 run.sh 尾部已预留注释掉的挂载点，手动启用时取消注释即可。

用法：
  python3 cross_review.py --topic "沙漏同步方案" \
      --options "A:重跑sync;B:加unique约束;C:双写" --tendency "B"   # 发送（需 CROSS_REVIEW=1）
  python3 cross_review.py --scan-only       # 只扫描回传意见并落沙（不发送）
  python3 cross_review.py --dry-run         # 预览脱敏摘要，不发送不扫描
  python3 cross_review.py --self-test

环境变量：
  CROSS_REVIEW=1        启用发送（默认禁用）
  NEXSANDBASE_HOME      沙漏数据目录
  CROSS_REVIEW_URL      对端注入地址（默认 http://jiali.tdx1146.com:18888/api/inject）
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# ── 路径 ─────────────────────────────────────────────────────
_SOURCE_DIR = "/vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source"
_SANDBASE_HOME = os.environ.get(
    "NEXSANDBASE_HOME",
    "/vol2/1000/AI专用/所有自动化/轻如烟/sandglass",
)
os.environ.setdefault("NEXSANDBASE_HOME", _SANDBASE_HOME)
_SANDGLASS_TXT = os.path.join(_SANDBASE_HOME, "sandglass.txt")
_OP_LOG = "/vol2/1000/AI专用/Agent OS/iso-sand/data/operation_log.jsonl"

INJECT_URL = os.environ.get(
    "CROSS_REVIEW_URL", "http://jiali.tdx1146.com:18888/api/inject"
)
TAG = "旁观者-洞察"
FORM = "C"                      # 他者旁观者（跨实例）
SCAN_WINDOW_MIN = 60            # 回传扫描窗口：最近 1 小时
REPLY_KEYWORD = "互审"           # 妹妹回复须含该关键词（防误吞其他 sister 消息）
_DEDUPE_SCAN_LINES = 60
_OPINION_MAX = 400

# 脱敏模式（决策摘要不得含敏感路径 / 密钥 / 内网地址）
_SENSITIVE_PATTERNS = [
    re.compile(r"/vol\d+/[^\s；;，,。！？\"']+"),     # 绝对路径 /vol1 /vol2 ...
    re.compile(r"/tmp/[^\s；;，,。！？\"']+"),          # /tmp 路径
    re.compile(r"/home/[^\s；;，,。！？\"']+"),         # /home 路径
    re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),        # IPv4
    re.compile(r"\bsk-[^\s；;，,。！？\"']+"),                       # sk- 类 API key（含 sk-proj-xxx 带连字符）
    re.compile(r"\bsk_[^\s；;，,。！？\"']+"),                        # sk_ 类（stripe 测试 key 等）
    re.compile(r"\b[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}(?:\.[A-Za-z0-9_-]+)?\b"),  # JWT/签名令牌（须在长串之前，防分段蚕食）
    re.compile(r"\b[A-Za-z0-9]{24,}\b"),                              # 长随机串（≥24位字母数字=密钥/令牌）
    re.compile(r"(?i)\b(api[_-]?key|apikey|token|secret|password|passwd)\b\s*[=:：]\s*\S+"),
    re.compile(r"(?i)\b(?:key|token|secret|password)\b[\"']?\s*[:=]\s*[\"'][^\"']+[\"']"),
    re.compile(r"jiali\d*\s*[：:]\s*\S+"),             # jiali3:xxx 类 key 记录
]
_PORT_PATTERN = re.compile(r":\d{4,5}\b")              # 端口号（:18888 等）
_PORT_CN_PATTERN = re.compile(r"(?:端口|端口号|port)\s*[:：]?\s*\d{4,5}\b")  # 端口 18888 / 端口号:18888


def sanitize(text: str) -> str:
    """脱敏：移除路径/密钥/内网地址/端口，保留决策语义。"""
    if not text:
        return text
    out = text
    for pat in _SENSITIVE_PATTERNS:
        out = pat.sub("【脱敏】", out)
    out = _PORT_PATTERN.sub("", out)
    out = _PORT_CN_PATTERN.sub("【脱敏】", out)
    # 折叠连续空白与【脱敏】重复
    out = re.sub(r"(【脱敏】\s*)+", "【脱敏】", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def build_summary(topic: str, options: str, tendency: str, note: str = "") -> dict:
    """组装脱敏决策摘要。options 形如 "A:方案一;B:方案二;C:方案三"。"""
    opts = [o.strip() for o in re.split(r"[;；]", options) if o.strip()]
    summary = {
        "topic": sanitize(topic)[:80],
        "options": [sanitize(o)[:120] for o in opts[:3]],
        "tendency": sanitize(tendency)[:60],
    }
    if note:
        summary["note"] = sanitize(note)[:200]
    return summary


def build_message(summary: dict) -> str:
    """格式参照现有跨实例消息：注入一行文本到对端会话。"""
    opts = "；".join(summary["options"]) if summary["options"] else "（未提供选项）"
    msg = (
        f"[姐姐→妹妹] 跨实例互审请求: 决策主题: {summary['topic']}；"
        f"选项: {opts}；我的倾向: {summary['tendency']}。"
    )
    if summary.get("note"):
        msg += f"背景: {summary['note']}。"
    msg += "请审查并回复（回复请含「互审」以便识别）。"
    return msg


# ═══════════════════ 发送（默认禁用） ═══════════════════

def send(summary: dict) -> dict:
    """POST /api/inject。失败静默（妹妹机器不可达是常态）。"""
    if os.environ.get("CROSS_REVIEW") != "1":
        return {"ok": False, "reason": "disabled", "hint": "CROSS_REVIEW=1 启用"}
    msg = build_message(summary)
    payload = json.dumps({"message": msg}).encode("utf-8")
    req = urllib.request.Request(
        INJECT_URL, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:300]
        return {"ok": True, "reason": "sent", "resp": body}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "reason": f"unreachable: {type(e).__name__}", "detail": str(e)[:200]}


# ═══════════════════ 回传扫描 ═══════════════════

def scan_replies(window_min: int = SCAN_WINDOW_MIN) -> list:
    """扫描沙漏最近 window_min 分钟内妹妹的回复（sender∈{sister,user} 且含"互审"）。"""
    if not os.path.exists(_SANDGLASS_TXT):
        return []
    try:
        with open(_SANDGLASS_TXT, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    now = datetime.now()
    out = []
    for ln in lines:
        m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\S+) \| (.*)$", ln)
        if not m:
            continue
        ts_s, sender, text = m.group(1), m.group(2), m.group(3)
        if sender not in ("sister", "user"):
            continue
        if REPLY_KEYWORD not in text:
            continue
        try:
            ts = datetime.strptime(ts_s[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        age = (now - ts).total_seconds()
        # 5 秒容差：避免边界抖动（截断到秒后恰好在窗口边缘的条目被误判）
        if age > window_min * 60 + 5 or age < -5:
            continue
        out.append({"ts": ts_s, "sender": sender, "text": text[:_OPINION_MAX]})
    return out


def persist_opinion(opinion: dict) -> dict:
    """意见写沙漏（tag=旁观者-洞察，actor=cross-instance）。指纹去重幂等。"""
    text = opinion["text"]
    fp = hashlib.sha1(text[:60].encode("utf-8")).hexdigest()[:12]

    # 去重：沙漏最近条目已有同指纹则不重复落沙
    if os.path.exists(_SANDGLASS_TXT):
        try:
            with open(_SANDGLASS_TXT, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                chunk = max(8192, size)
                f.seek(max(0, size - chunk))
                data = f.read().decode("utf-8", errors="ignore")
            recent = data.splitlines()[-_DEDUPE_SCAN_LINES:]
            for ln in recent:
                if fp in ln or (text[:30] in ln and "跨实例互审" in ln):
                    return {"written": False, "reason": "dedupe_hit", "fingerprint": fp}
        except OSError:
            pass

    line = (
        f"【旁观者洞察】跨实例互审回传（{opinion['ts']} {opinion['sender']}）：{text}；"
        f"actor=cross-instance form={FORM} status=pending；tag={TAG}"
    )
    sys.path.insert(0, _SOURCE_DIR)
    try:
        from sandglass_log import log_message
        ok = log_message(line, sender="agent")
        return {"written": ok, "reason": "ok" if ok else "sandglass_write_failed", "fingerprint": fp}
    except Exception as e:
        return {"written": False, "reason": f"error: {e}", "fingerprint": fp}


# ═══════════════════ operation_log ═══════════════════

def log_op(level: str, action: str, result: str, detail: str) -> None:
    try:
        rec = {
            "t": datetime.now().isoformat(),
            "level": level,
            "actor": "cross_review",
            "action": action,
            "target": "cross_instance",
            "result": result,
            "detail": detail,
        }
        with open(_OP_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ═══════════════════ 主流程 ═══════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="跨实例互审（P3.3）")
    parser.add_argument("--topic", help="决策主题")
    parser.add_argument("--options", help="选项，分号分隔，如 'A:方案一;B:方案二;C:方案三'")
    parser.add_argument("--tendency", help="我的倾向，如 'B' 或 '倾向方案二'")
    parser.add_argument("--note", default="", help="背景补充（可选，会脱敏）")
    parser.add_argument("--scan-only", action="store_true", help="只扫描回传意见并落沙，不发送")
    parser.add_argument("--dry-run", action="store_true", help="只预览脱敏摘要，不发送不扫描")
    parser.add_argument("--window-min", type=int, default=SCAN_WINDOW_MIN, help="回传扫描窗口（分钟）")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    # ── 回传处理（发送后/独立运行都执行）─────────────────
    replies = scan_replies(args.window_min)
    persisted = 0
    for op in replies:
        r = persist_opinion(op)
        if r["written"]:
            persisted += 1
    if replies:
        log_op("INFO", "cross_review_scan", "OK",
               f"window={args.window_min}min replies={len(replies)} persisted={persisted}")

    if args.dry_run:
        if args.topic:
            summary = build_summary(args.topic, args.options or "", args.tendency or "")
            print(json.dumps({
                "dry_run": True,
                "summary": summary,
                "message": build_message(summary),
                "sanitized": sanitize(
                    f"{args.topic} {args.options} {args.tendency} {args.note}"),
            }, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"dry_run": True, "replies_found": len(replies),
                              "persisted": persisted}, ensure_ascii=False))
        return 0

    # ── 发送（仅手动指定决策参数时）──────────────────────
    if not args.scan_only:
        if not args.topic:
            print(json.dumps({"ok": False, "reason": "missing_topic",
                              "hint": "需 --topic；或 --scan-only 只扫回传"},
                             ensure_ascii=False))
            return 1
        summary = build_summary(args.topic, args.options or "", args.tendency or "", args.note)
        result = send(summary)
        result["message_preview"] = build_message(summary)[:120]
        log_op("INFO" if result["ok"] else "WARN", "cross_review_send",
               "OK" if result["ok"] else "SKIP", f"topic={summary['topic'][:40]} {result.get('reason')}")
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps({"scan_only": True, "replies_found": len(replies),
                          "persisted": persisted}, ensure_ascii=False))
    return 0


def self_test() -> int:
    print("跨实例互审自检")
    ok = True

    # 1. 脱敏
    dirty = "方案B的路径 /vol1/@apphome/trim.openclaw/data/workspace 和 /vol2/1000/secret 以及 key: sk-abc1234567890，端口 18888，IP 192.168.0.149"
    clean = sanitize(dirty)
    ok &= "/vol1" not in clean and "/vol2" not in clean
    ok &= "sk-" not in clean and "192.168" not in clean and "18888" not in clean
    ok &= "方案B" in clean
    print(f"  ✅ 脱敏: {clean!r}")
    ok &= "【脱敏】" in clean

    # 2. 摘要组装 + 消息格式
    s = build_summary("沙漏同步方案", "A:重跑sync;B:加unique约束;C:双写", "B", "妹妹上次提到的幂等性问题")
    ok &= len(s["options"]) == 3 and s["tendency"] == "B"
    msg = build_message(s)
    ok &= msg.startswith("[姐姐→妹妹] 跨实例互审请求") and "互审" in msg
    print(f"  ✅ 消息: {msg[:90]}…")

    # 3. 禁用时 send 不真发
    r = send(s)
    ok &= r["ok"] is False and r["reason"] == "disabled"
    print(f"  ✅ 默认禁用: {r['reason']}")

    # 4. 选项截断（>3 个只留前 3）
    s2 = build_summary("t", "A:1;B:2;C:3;D:4", "A")
    ok &= len(s2["options"]) == 3
    print(f"  ✅ 选项上限 3: {len(s2['options'])}")

    # 5. 扫描（真实沙漏，不落沙——只验证管道）
    replies = scan_replies(60)
    print(f"  ✅ 回传扫描（真实数据，最近1h）: {len(replies)} 条")

    print(f"\n自检 {'通过' if ok else '失败'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
