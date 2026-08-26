#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
session-reset-watchdog.py — 会话重置看门狗
检测 OpenClaw 网关的自动会话重置（*.jsonl.reset.* 归档出现），
自动把归档复制为 *.restored.jsonl 供编辑器浏览，并记录日志。
用法: python3 session-reset-watchdog.py   （建议 cron 每 1-2 分钟跑一次）

2026-08-10 部署统一化：
  路径从 Agent OS/env.local 读取（RESET_WATCHDOG_SESSIONS_DIR /
  RESET_WATCHDOG_STATE_FILE / RESET_WATCHDOG_LOG_FILE），env.local 缺失时
  按脚本位置相对推导（state/log 在轻如烟/memory 下），仅 OpenClaw sessions
  目录保留机器级默认值作兜底。
"""
import os, glob, shutil, time, json, re

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIGHT_HOME = os.path.dirname(_HERE)


def _load_env_local():
    """加载 Agent OS 统一配置（env.local）。失败静默；仅补充未显式设置的变量。"""
    try:
        ao = os.environ.get("AGENT_OS_HOME", "")
        if not ao:
            cand = os.path.join(_LIGHT_HOME, "..", "Agent OS")
            if os.path.isdir(cand):
                ao = cand
        if not ao or not os.path.isfile(os.path.join(ao, "env.local")):
            return
        with open(os.path.join(ao, "env.local"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if not k or k in os.environ:
                    continue
                # 展开 ${VAR} 引用（env.local 内派生变量），多轮直到稳定
                for _ in range(5):
                    nv = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}",
                                lambda m: os.environ.get(m.group(1), ""), v)
                    if nv == v:
                        break
                    v = nv
                os.environ[k] = v
    except Exception:
        pass


_load_env_local()

SESSIONS_DIR = os.environ.get(
    "RESET_WATCHDOG_SESSIONS_DIR",
    os.path.join(os.path.expanduser("~"), ".openclaw", "agents", "main", "sessions"),
)
# 注：sessions 目录机器相关，正式部署请经 env.local 的 RESET_WATCHDOG_SESSIONS_DIR 配置；
# 此处兜底为 ~/.openclaw/agents/main/sessions（可移植，不硬编码任何生产路径）。
STATE_FILE = os.environ.get(
    "RESET_WATCHDOG_STATE_FILE",
    os.path.join(_LIGHT_HOME, "memory", "reset-watchdog-state.json"),
)
LOG_FILE = os.environ.get(
    "RESET_WATCHDOG_LOG_FILE",
    os.path.join(_LIGHT_HOME, "memory", "reset-watchdog.log"),
)


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    # 已处理过的归档集合
    seen = set()
    if os.path.exists(STATE_FILE):
        try:
            seen = set(json.load(open(STATE_FILE, encoding="utf-8")))
        except Exception:
            seen = set()

    resets = sorted(glob.glob(os.path.join(SESSIONS_DIR, "*.jsonl.reset.*")))
    fresh = []
    for rp in resets:
        name = os.path.basename(rp)
        if name not in seen:
            fresh.append(rp)
            seen.add(name)

    for rp in fresh:
        base = os.path.basename(rp)
        # 提取原会话 id: xxx.jsonl.reset.TS -> xxx
        sid = base.split(".jsonl.reset.")[0]
        restored = os.path.join(SESSIONS_DIR, f"{sid}.restored.jsonl")
        try:
            # 跳过归档自带的 session meta 行（保留消息，避免双 session 头）
            lines = open(rp, encoding="utf-8", errors="replace").readlines()
            body = [l for l in lines if not l.lstrip().startswith('{"type":"session"')]
            with open(restored, "w", encoding="utf-8") as f:
                f.writelines(body)
            log(f"🛟 检测到会话重置 {base} → 已恢复为可浏览 {os.path.basename(restored)} ({len(body)} 条)")
        except Exception as e:
            log(f"❌ 恢复失败 {base}: {e}")

    # 也把 restore 文件纳入状态，避免重复处理同名归档
    try:
        json.dump(sorted(seen), open(STATE_FILE, "w", encoding="utf-8"))
    except Exception:
        pass

    if fresh:
        log(f"本轮处理 {len(fresh)} 个重置归档")
    else:
        # 静默（正常无重置）
        pass


if __name__ == "__main__":
    main()
