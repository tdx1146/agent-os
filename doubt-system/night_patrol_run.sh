#!/bin/bash
# ============================================================
# night_patrol_run.sh — L4 夜巡执行器（自我怀疑系统 P2.3）
#
# 流程：
#   1. python3 night_patrol.py        → /tmp/night_patrol_input.json（纯数据，不调 LLM）
#   2. openclaw agent（隔离子代理）    → 读当天数据，产出 findings 到 /tmp/night_patrol_findings.json
#   3. night_patrol_findings.py       → 校验/去重/写沙漏(tag=旁观者-警讯)/高价值项追加 observer-alerts.json
#   4. night_patrol_dogma.py          → 反教条复核（P3.3）：top10 高频记忆“可能已过时？”≤3条/天
#   5. [可选] cross_review.py         → 跨实例互审（P3.3，默认注释，CROSS_REVIEW=1 启用）
#
# 调度：
#   - crontab: 30 23 * * *（立即生效，参照 agentos-services-check.sh 方式）
#   - task_rules.yaml 第7任务（下次调度器重启后生效，与现有调度器咬合）
#   - 每日幂等：marker 文件记录当天已跑，双调度源（cron+scheduler）同天只分析一次
#
# 手动强制重跑：night_patrol_run.sh --force
# 管道自检（不调 LLM、不写 marker）：NIGHT_PATROL_DRY=1 night_patrol_run.sh
# ============================================================

# ── 环境（cron 下 HOME/PATH 可能与交互 shell 不同，必须显式）──
export HOME=/vol1/@apphome/trim.openclaw/data/home
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin
export NEXSANDBASE_HOME="/vol2/1000/AI专用/所有自动化/轻如烟/sandglass"

WORKSPACE=/vol1/@apphome/trim.openclaw/data/workspace
SCRIPTS="$WORKSPACE/scripts"
LOG_DIR="$WORKSPACE/logs"
OP_LOG="/vol2/1000/AI专用/Agent OS/iso-sand/data/operation_log.jsonl"
RUN_LOG="$LOG_DIR/night-patrol.log"
MARKER="$LOG_DIR/night_patrol.last_run"
LOCK=/tmp/night_patrol.lock
INPUT=/tmp/night_patrol_input.json
FINDINGS=/tmp/night_patrol_findings.json
AGENT_OUT="$LOG_DIR/night-patrol-agent.out"

mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $1" >> "$RUN_LOG"; }

# ── operation_log 记录（与 iso_logger 同格式）─────────────────
log_op() {
  # $1=level $2=actor $3=action $4=result $5=detail
  python3 - "$1" "$2" "$3" "$4" "$5" <<'PYEOF'
import json, sys
from datetime import datetime
level, actor, action, result, detail = sys.argv[1:6]
rec = {"t": datetime.now().isoformat(), "level": level.upper(), "actor": actor,
       "action": action, "target": "night_patrol", "result": result, "detail": detail}
with open("/vol2/1000/AI专用/Agent OS/iso-sand/data/operation_log.jsonl",
          "a", encoding="utf-8") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
PYEOF
}

# ── 单实例锁（cron + scheduler 同分钟并发时只跑一个）──────────
exec 9>"$LOCK"
if ! flock -n 9; then
    log "另一实例正在运行，跳过"
    exit 0
fi

DATE=$(date +%F)

# ── 每日幂等：今天已成功跑过则跳过（--force 可重跑）──────────
if [ "${1:-}" != "--force" ] && [ -f "$MARKER" ] && [ "$(cat "$MARKER" 2>/dev/null)" = "$DATE" ]; then
    log "今日($DATE)夜巡已完成，跳过（如需重跑: night_patrol_run.sh --force）"
    exit 0
fi

log "== 夜巡启动 $DATE =="

# ── 1. 数据汇总（不调 LLM）────────────────────────────────────
if ! python3 "$SCRIPTS/night_patrol.py" --date "$DATE" --output "$INPUT" >> "$RUN_LOG" 2>&1; then
    log "数据汇总失败"
    log_op ERROR night_patrol data_prep FAIL "night_patrol.py 退出码非0，夜巡中止"
    exit 1
fi
log_op INFO night_patrol data_prep OK "input=$INPUT date=$DATE"

# ── 管道自检模式：只验证数据准备 + 日志，不调 LLM ────────────
if [ "${NIGHT_PATROL_DRY:-0}" = "1" ]; then
    log "DRY 模式：跳过子代理分析与回流（不调 LLM，不写 marker）"
    log_op INFO night_patrol dry_run OK "NIGHT_PATROL_DRY=1 管道自检完成"
    exit 0
fi

# ── 2. 触发隔离子代理（时间旁观者，独立上下文）────────────────
PROMPT=$(cat <<'EOF'
你是 Agent OS 的【夜巡·时间旁观者】（form=B，隔离子代理，独立上下文）。
现在是 23:30，你回看 __DATE__ 全天的运行数据，找出白天当局者（主AI）忽略的矛盾、模式与被遗漏的教训。

【步骤】
1. 用 read 工具读取 /tmp/night_patrol_input.json（夜巡数据汇总：当天对话原文/operation_log 变更与异常/crontab 快照/怀疑账本/topic_risk/memory 文件）。
2. 分析并产出 findings（发现）。每条 finding 必须满足：
   - 有 evidence：沙漏记录 id、对话原文摘录、或 operation_log 行号。无证据的发现直接丢弃（证据强制铁律）。
   - 只写"低置信假设"或"需复核信号"，禁止写死结论性教训（防回声室）。
   - 字段：t=ISO时间, actor=observer-night-patrol-__DATE_COMPACT__, form="B", tag="旁观者-警讯",
     severity(1-5整数), confidence(0-1), evidence, topic(主题词), suggestion(具体可执行动作), status="pending"
   - confidence 规则：基于用户纠正/操作失败/工具报错=0.7+；单旁观者洞察=0.5。
3. 【部署怀疑重点】crontab_snapshot 与 fails 中 kind=CHANGE 的条目必须检查：
   - crontab 关键条目是否齐全（has_pulse/has_night_patrol/has_watchdog 若为 false 是高危信号）
   - 当天部署/重启/配置变更是否自洽（有变更但无对应验证、有 FAIL 但无人跟进）
   - 部署类变更若无 FAIL 但影响面大（crontab/配置/路径），仍应产出低置信复核信号
4. 用 write 工具把 findings 写到 /tmp/night_patrol_findings.json，格式：
   {"date":"__DATE__","findings":[{...}, ...]}（无发现则 findings: []）
5. 聚焦今天数据，不编造。除写 findings JSON 文件外，不要修改任何系统文件、不写沙漏、不写 operation_log。
EOF
)
PROMPT=${PROMPT//__DATE__/$DATE}
PROMPT=${PROMPT//__DATE_COMPACT__/${DATE//-/}}

log "触发隔离子代理分析 (session=night-patrol)"
# 注意：CLI 的 gateway 通道需要设备 scope 审批（operator.write，一次性）；
# 未审批时自动走 embedded 回退（本地运行 agent，工具可用，已实测 read/write 正常）。
# 该 build 的 embedded 回退固定退出码 2（Bad substitution 构建缺陷），
# 因此以 /tmp/night_patrol_findings.json 是否产出作为成功判据，而非退出码。
timeout 1000 openclaw agent --session-id night-patrol --message "$PROMPT" \
    --timeout 900 --thinking low > "$AGENT_OUT" 2>&1
AGENT_RC=$?

if [ -f "$FINDINGS" ]; then
    log "子代理完成（rc=$AGENT_RC，findings 已产出）"
    log_op INFO night_patrol agent_turn OK "session=night-patrol rc=$AGENT_RC findings=yes"
elif [ $AGENT_RC -eq 124 ] || [ $AGENT_RC -eq 137 ]; then
    log "子代理超时 rc=$AGENT_RC（见 $AGENT_OUT）"
    log_op WARN night_patrol agent_turn TIMEOUT "rc=$AGENT_RC 未产出 findings"
    exit 1
else
    log "子代理未产出 findings rc=$AGENT_RC（见 $AGENT_OUT）"
    log_op WARN night_patrol agent_turn FAIL "rc=$AGENT_RC 分析未完成，findings 未回流"
    exit 1
fi

# ── 3. 回流：校验/去重/写沙漏/警讯级追加 ──────────────────────
if [ -f "$FINDINGS" ]; then
    PERSIST_OUT=$(python3 "$SCRIPTS/night_patrol_findings.py" --input "$FINDINGS" 2>&1)
    PERSIST_RC=$?
    log "回流结果 rc=$PERSIST_RC: $PERSIST_OUT"
    if [ $PERSIST_RC -eq 0 ]; then
        log_op INFO night_patrol findings_persist OK "$PERSIST_OUT"
    else
        log_op ERROR night_patrol findings_persist FAIL "$PERSIST_OUT"
    fi
    rm -f "$FINDINGS"
else
    log "无 findings 文件（子代理未产出），跳过回流"
    log_op INFO night_patrol findings_persist SKIP "findings 文件不存在"
fi

# ── 4. 反教条复核（P3.3 增强夜巡：top10 高频记忆"可能已过时？"复核）──
#    低频（默认≤3条/天）+ 带证据（memory_id）+ 幂等（指纹去重+当日状态文件）
if [ -f "$SCRIPTS/night_patrol_dogma.py" ]; then
    DOGMA_OUT=$(python3 "$SCRIPTS/night_patrol_dogma.py" 2>&1)
    DOGMA_RC=$?
    log "反教条复核 rc=$DOGMA_RC: $DOGMA_OUT"
    if [ $DOGMA_RC -eq 0 ]; then
        log_op INFO night_patrol dogma_review OK "$DOGMA_OUT"
    else
        log_op ERROR night_patrol dogma_review FAIL "$DOGMA_OUT"
    fi
else
    log "反教条脚本缺失，跳过"
    log_op WARN night_patrol dogma_review SKIP "night_patrol_dogma.py 不存在"
fi

# ── 5. 跨实例互审（P3.3，可选，默认禁用）────────────────────────
#    妹妹机器时段性不可达是常态；手动启用：取消注释 + 设 CROSS_REVIEW=1
#      CROSS_REVIEW=1 python3 "$SCRIPTS/cross_review.py" --scan-only
#    或单独手动运行：python3 "$SCRIPTS/cross_review.py" --topic "决策主题" \
#      --options "A:方案一;B:方案二;C:方案三" --tendency "B"
# if [ "${CROSS_REVIEW:-0}" = "1" ] && [ -f "$SCRIPTS/cross_review.py" ]; then
#     CR_OUT=$(python3 "$SCRIPTS/cross_review.py" --scan-only 2>&1)
#     CR_RC=$?
#     log "跨实例互审 rc=$CR_RC: $CR_OUT"
#     log_op INFO night_patrol cross_review OK "$CR_OUT"
# else
#     log "跨实例互审跳过（CROSS_REVIEW=1 启用）"
# fi

# ── 完成标记（当天幂等）───────────────────────────────────────
echo "$DATE" > "$MARKER"
log "== 夜巡完成 $DATE =="
exit 0
