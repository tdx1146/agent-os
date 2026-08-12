#!/bin/bash
# pulse-cron.sh — 沙漏自治脉冲（Phase6 重建，2026-08-04）
# ======================================================
# 原文件缺失但 crontab 每 10 分钟仍在调用（审计断口②：沙漏自治停搏 8/2）。
# 重建为：调用 scripts/self_pulse_cli.py 触发自主脉冲 + 更新 /tmp/pulse-status.json。
# v2（2026-08-05 真任务化）：self_pulse_cli.py 输出分级——正常态只写
# metrics.jsonl 不写 sandglass.txt；漂移/新待办才写 sandglass.txt + 发总线事件。
# v3（2026-08-10 部署统一化）：NEXSANDBASE_HOME 从 Agent OS/env.local 读取，
#   缺失时按脚本位置相对推导（$LIGHT_HOME/sandglass），零硬编码。
#
# 部署：crontab 已有条目，无需改 crontab：
#   */10 * * * * /vol2/1000/AI专用/所有自动化/轻如烟/scripts/pulse-cron.sh

# 2026-08-11（阶段2 前置）：crontab 环境的 HOME 来自 passwd（/home/trim.openclaw），
# 找不到 openclaw.json → inject-helper.mjs / edit-web.py 读不到 gateway.auth.token/port，
# B 通道（inject chat.send）认证失败（历史 9 连败根因，见 Agent OS/docs/DIAG-自动唤醒-20260807.md）。
# 约定：OPENCLAW_HOME = 含 openclaw.json 的目录（与 edit-web.py / inject-helper.mjs 一致）。
# env.local（下方 set -a 源入）若定义 OPENCLAW_HOME 则优先（配置中心为准）；
# 兜底用 $HOME/.openclaw（可移植；本仓版本不硬编码任何生产路径）。
export OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LIGHT_HOME="$(cd "$SCRIPT_DIR/.." && pwd)"
_AGENT_OS="${AGENT_OS_HOME:-}"
if [ -z "$_AGENT_OS" ] && [ -d "$LIGHT_HOME/../Agent OS" ]; then
    _AGENT_OS="$(cd "$LIGHT_HOME/../Agent OS" && pwd)"
fi
if [ -n "$_AGENT_OS" ] && [ -f "$_AGENT_OS/env.local" ]; then
    set -a; . "$_AGENT_OS/env.local"; set +a
fi
export NEXSANDBASE_HOME="${NEXSANDBASE_HOME:-$LIGHT_HOME/sandglass}"
export SANDGLASS_SOURCE="${SANDGLASS_SOURCE:-$LIGHT_HOME/sandglass_source}"

# 1. 自主脉冲（self_pulse：推进待办 / 画像漂移检查；输出分级见 CLI 文档）
OUT=$(python3 "$SCRIPT_DIR/self_pulse_cli.py" 2>/dev/null)
RC=$?

# 2. 更新状态文件（保留其他字段）
TS=$(date '+%H:%M')
python3 - "$TS" "$RC" "$OUT" << 'PYEOF' 2>/dev/null || true
import json, sys
ts, rc, out = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    d = json.load(open('/tmp/pulse-status.json'))
except Exception:
    d = {}
d['last_pulse'] = ts
d['pulse_rc'] = int(rc)
try:
    d['pulse_result'] = json.loads(out)
except Exception:
    d['pulse_result'] = out[:200]
json.dump(d, open('/tmp/pulse-status.json', 'w'))
PYEOF

exit 0
