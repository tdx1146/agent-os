#!/bin/bash
# 轻如烟编辑器自愈脚本（agent-os 分发的可移植版；bootstrap 接线到 $EDITOR_HOME）
# 2026-08-13（R-1）：随 agent-os 分发，由 deploy.sh bootstrap 幂等复制到编辑器目录
#   （$LIGHT_HOME/scripts/health-check.sh），cron `*/5` 调用 —— 修复新机器"自愈 cron 指向空"。
# 路径来源：Agent OS/env.local（配置中心）；缺失时按脚本位置相对推导（零硬编码）。

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LIGHT_HOME="$(cd "$SCRIPT_DIR/.." && pwd)"
# 统一配置加载（Agent OS 为同布局兄弟目录；找不到则用自身相对推导）
_AGENT_OS="${AGENT_OS_HOME:-}"
if [ -z "$_AGENT_OS" ] && [ -d "$LIGHT_HOME/../Agent OS" ]; then
    _AGENT_OS="$(cd "$LIGHT_HOME/../Agent OS" && pwd)"
fi
if [ -n "$_AGENT_OS" ] && [ -f "$_AGENT_OS/env.local" ]; then
    set -a; . "$_AGENT_OS/env.local"; set +a
fi
EDITOR_HOME="${EDITOR_HOME:-$LIGHT_HOME/scripts}"
EDITOR_PORT="${EDITOR_PORT:-18888}"
LOG="/tmp/pulse-status.json"
TS=$(date '+%Y-%m-%d %H:%M')

# 1. 检查编辑器（端口 $EDITOR_PORT）
if ! curl -sf "http://127.0.0.1:$EDITOR_PORT/" > /dev/null 2>&1; then
    if [ -f "$EDITOR_HOME/edit-web.py" ]; then
        cd "$LIGHT_HOME" && nohup python3 "$EDITOR_HOME/edit-web.py" > /tmp/edit-web-restart.log 2>&1 &
        echo "[$TS] 🩺 自愈：编辑器挂了 → 已重启 (PID $!)" >> "$LOG"
    else
        echo "[$TS] ⚠️ 编辑器未运行且脚本缺失，跳过自愈" >> "$LOG"
    fi
fi

# 2. 检查 sandglass MCP（端口 8765，如果有 socat 版的话）
if ! curl -sf http://127.0.0.1:8765/ > /dev/null 2>&1; then
    # socat 版可能不跑 HTTP，跳过
    true
fi
