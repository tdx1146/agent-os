#!/bin/bash
# =============================================================
# system_health_check.sh — Agent OS 全系统健康巡检（只读）
# -------------------------------------------------------------
# 遍历全部组件：沙漏 / LMS / 胶水层 / 总线 / 玄鉴 / 夜巡 /
#             self_pulse 唤醒链 / OpenClaw 插件 / 备份 / cron 完整性
# 每项输出：✅/⚠️/❌ + 关键数字 + 判定依据；末尾汇总表。
#
# 用法：
#   bash system_health_check.sh            # 手动巡检（stdout 报告；不改任何状态）
#   bash system_health_check.sh --cron     # cron 模式：追加日志 + 状态变化才告警
#                                          #   （供 crontab 每 30min 调用）
#
# 退出码：0=全绿  1=有警告  2=有故障（便于外部捕获）
#
# 设计纪律：
#   - 零硬编码：所有绝对路径来自 Agent OS/env.local，缺失时相对推导
#   - 只读：不写任何系统数据文件，不调用任何写接口
#   - cron 告警去重：用 run/system_health.state 记录上次结果，
#     只有「绿→黄/红」才写 🚨 告警行，恢复时写 ✅ 行
# =============================================================
set -u

# ---------- 配置加载（唯一来源 env.local，缺失时相对推导） ----------
AGENT_OS_HOME="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$AGENT_OS_HOME/env.local" ]; then
    set -a; . "$AGENT_OS_HOME/env.local"; set +a
fi

SANDGLASS_API_PORT="${SANDGLASS_API_PORT:-17333}"
LMS_API_PORT="${LMS_API_PORT:-8190}"
LMS_CONTROL_PORT="${LMS_CONTROL_PORT:-8191}"
GLUE_PORT="${GLUE_PORT:-19000}"
ISO_SAND_HOME="${ISO_SAND_HOME:-$AGENT_OS_HOME/iso-sand}"
RUN_DIR="${RUN_DIR:-$AGENT_OS_HOME/run}"
LOG_DIR="${LOG_DIR:-$AGENT_OS_HOME/logs}"
# 玄鉴已并入 agent-os/xuanjian（2026-08-12）；优先新路径，旧同构沙盘回退（本机运行实例仍在其 data/）。
if [ -d "$AGENT_OS_HOME/xuanjian/src" ]; then
    VERIFY_HOME="${VERIFY_HOME:-$AGENT_OS_HOME/xuanjian}"
else
    VERIFY_HOME="${VERIFY_HOME:-$AGENT_OS_HOME/../AgentOS-IsoSand/同构沙盘}"
fi
NEXSANDBASE_HOME="${NEXSANDBASE_HOME:-$AGENT_OS_HOME/../所有自动化/轻如烟/sandglass}"
LIGHT_HOME="${LIGHT_HOME:-$AGENT_OS_HOME/../所有自动化/轻如烟}"
LMS_HOME="${LMS_HOME:-$AGENT_OS_HOME/../living-memory-system-cloud}"
GLUE_HOME="${GLUE_HOME:-$AGENT_OS_HOME/../memory-integration-layer}"
# 夜巡 marker 所在 workspace（由 env.local 的 FACTS_DICT_PATH 推导）
if [ -n "${FACTS_DICT_PATH:-}" ]; then
    WORKSPACE="$(dirname "$(dirname "$FACTS_DICT_PATH")")"
else
    WORKSPACE="/vol1/@apphome/trim.openclaw/data/workspace"
fi

# 备份根目录（由 LMS_HOME 同级推导，不硬编码）
BACKUP_ROOT="$(dirname "$LMS_HOME")/backups/lms"

MODE="${1:-manual}"
NOW=$(date +%s)
NOW_ISO=$(date '+%F %T')
RES=$(mktemp)
STATE_FILE="$RUN_DIR/system_health.state"
HL_LOG="$LOG_DIR/system_health.log"
LMS_LOG_DIR="$LMS_HOME/logs"

# ---------- 工具函数 ----------
ok()    { printf '%s|OK|%s\n' "$1" "$2" >> "$RES"; }
warn()  { printf '%s|WARN|%s\n' "$1" "$2" >> "$RES"; }
fault() { printf '%s|FAULT|%s\n' "$1" "$2" >> "$RES"; }

file_age() { # 文件/目录秒数年龄；不存在=999999
    local f="$1"
    if [ -e "$f" ]; then
        echo $(( NOW - $(stat -c %Y "$f" 2>/dev/null || echo "$NOW") ))
    else
        echo 999999
    fi
}

age_label() { # 秒数 → 人类可读
    local s="$1"
    if [ "$s" -ge 86400 ]; then echo "$((s/86400))天前"
    elif [ "$s" -ge 3600 ]; then echo "$((s/3600))小时前"
    elif [ "$s" -ge 60 ]; then echo "$((s/60))分钟前"
    else echo "${s}秒前"; fi
}

emoji() { case "$1" in OK) echo "✅";; WARN) echo "⚠️";; FAULT) echo "❌";; esac; }

http_get() { curl -sf --max-time 6 "$1" 2>/dev/null; }

# =============================================================
# ① 沙漏 sandglass（明线保底）
# =============================================================
SG_TXT="$NEXSANDBASE_HOME/sandglass.txt"
SG_IDX="$NEXSANDBASE_HOME/sandglass.idx"
SG_METRICS="$NEXSANDBASE_HOME/metrics.jsonl"
SG_SALIENCE="$NEXSANDBASE_HOME/salience_state.json"
SG_SLEEP="$NEXSANDBASE_HOME/sleep_pressure.json"
SG_DOUBT="$NEXSANDBASE_HOME/doubt.db"

# 1.1 沙漏 API 存活
SG_HEALTH=$(http_get "http://127.0.0.1:$SANDGLASS_API_PORT/api/health")
if [ -n "$SG_HEALTH" ]; then
    SG_COUNT=$(echo "$SG_HEALTH" | python3 -c "import json,sys;print(json.load(sys.stdin).get('sandglass_count','?'))" 2>/dev/null)
    ok  "沙漏API" "端口 $SANDGLASS_API_PORT 健康，sandglass_count=$SG_COUNT"
else
    fault "沙漏API" "端口 $SANDGLASS_API_PORT 不可达（进程死了？）"
fi

# 1.2 落沙内容（对话驱动，30min 活跃 / 6h 静默警告 / 更久=断）
TXT_AGE=$(file_age "$SG_TXT")
if [ "$TXT_AGE" -lt 1800 ]; then
    ok "沙漏落沙" "sandglass.txt $(age_label $TXT_AGE) 有新落沙（活跃）"
elif [ "$TXT_AGE" -lt 21600 ]; then
    warn "沙漏落沙" "sandglass.txt $(age_label $TXT_AGE) 无新增（静默期，夜间正常；白天需注意）"
else
    fault "沙漏落沙" "sandglass.txt $(age_label $TXT_AGE) 无新增——明线可能断（失忆根源）"
fi

# 1.3 索引器
IDX_AGE=$(file_age "$SG_IDX")
if [ "$IDX_AGE" -lt 3600 ]; then
    ok "沙漏索引" "sandglass.idx $(age_label $IDX_AGE) 在更新（索引活着）"
elif [ "$IDX_AGE" -lt 7200 ]; then
    warn "沙漏索引" "sandglass.idx $(age_label $IDX_AGE) 偏旧"
else
    fault "沙漏索引" "sandglass.idx $(age_label $IDX_AGE) 停更——检索会退化"
fi

# 1.4 自治脉冲（metrics.jsonl 每 10min 由 self_pulse 写 = 落沙管线心跳）
M_AGE=$(file_age "$SG_METRICS")
if [ "$M_AGE" -lt 900 ]; then
    ok "沙漏自治" "metrics.jsonl $(age_label $M_AGE)（10min 心跳正常）"
elif [ "$M_AGE" -lt 1800 ]; then
    warn "沙漏自治" "metrics.jsonl $(age_label $M_AGE) 略旧"
else
    fault "沙漏自治" "metrics.jsonl $(age_label $M_AGE) 停更——self_pulse 或沙漏管线断了"
fi

# 1.5 显著性/体力状态（salience_gate + sleep_pressure 每 10min 更新）
SL_AGE=$(file_age "$SG_SALIENCE"); SP_AGE=$(file_age "$SG_SLEEP")
if [ "$SL_AGE" -lt 900 ] && [ "$SP_AGE" -lt 900 ]; then
    SP_MODE=$(python3 -c "import json;d=json.load(open('$SG_SLEEP'));print(d.get('mode','?'))" 2>/dev/null)
    ok "显著性/体力" "salience $(age_label $SL_AGE) + sleep_pressure $(age_label $SP_AGE)，体力模式=${SP_MODE:-?}"
elif [ "$SL_AGE" -lt 1800 ] || [ "$SP_AGE" -lt 1800 ]; then
    warn "显著性/体力" "salience $(age_label $SL_AGE) / sleep_pressure $(age_label $SP_AGE) 偏旧"
else
    fault "显著性/体力" "salience $(age_label $SL_AGE) / sleep_pressure $(age_label $SP_AGE) 停更"
fi

# 1.6 怀疑账本 doubt.db（事件驱动写，48h 内正常）
DB_AGE=$(file_age "$SG_DOUBT")
if [ "$DB_AGE" -lt 172800 ]; then
    ok "怀疑账本" "doubt.db $(age_label $DB_AGE) 有写入"
elif [ "$DB_AGE" -lt 604800 ]; then
    warn "怀疑账本" "doubt.db $(age_label $DB_AGE) 偏旧（夜巡/怀疑钩子可能没写）"
else
    fault "怀疑账本" "doubt.db $(age_label $DB_AGE) 长期未写——怀疑系统停摆"
fi

# =============================================================
# ② LMS 活体记忆（暗线核心）
# =============================================================
# 2.1 API 存活 + 主会话状态
LMS_HEALTH=$(http_get "http://127.0.0.1:$LMS_API_PORT/health")
LMS_STATUS=$(http_get "http://127.0.0.1:$LMS_API_PORT/status/main")
if [ -n "$LMS_HEALTH" ] && [ -n "$LMS_STATUS" ]; then
    LMS_META=$(echo "$LMS_STATUS" | python3 -c "
import json,sys
d=json.load(sys.stdin).get('status',{})
print('%s|%s|%s|%s' % (d.get('turn_count','?'), d.get('last_surprise','?'), d.get('entropy_ratio','?'), d.get('purpose_coherence','?')))
" 2>/dev/null)
    TC=$(echo "$LMS_META" | cut -d'|' -f1)
    SURP=$(echo "$LMS_META" | cut -d'|' -f2)
    ENT=$(echo "$LMS_META" | cut -d'|' -f3)
    PUR=$(echo "$LMS_META" | cut -d'|' -f4)
    if [ "$SURP" = "?" ]; then
        # last_surprise 缺席 = 重启后尚无对话轮（last_activation=None），语义正常，非降级
        ok "LMS-API" "轮次=$TC 惊讶=无对话未产生（正常） 熵比=$ENT 目的=$PUR"
    elif python3 -c "exit(0 if float('$SURP') >= 0 else 1)" 2>/dev/null; then
        ok "LMS-API" "轮次=$TC 惊讶=$SURP 熵比=$ENT 目的=$PUR（健康语义正常）"
    else
        warn "LMS-API" "轮次=$TC 惊讶=$SURP 异常（<0=降级/未修复语义）"
    fi
    # 轮次回退检测（与状态文件比对；无状态文件则跳过）
    PREV_TC=$(grep '^LMS-API|' "$STATE_FILE" 2>/dev/null | tail -1 | cut -d'|' -f3 | grep -oE '轮次=[0-9]+' | cut -d= -f2)
    if [ -n "${PREV_TC:-}" ] && [ "${TC:-0}" != "?" ] && [ "$TC" -lt "$PREV_TC" ] 2>/dev/null; then
        warn "LMS-API" "轮次回退：上次=$PREV_TC 现在=$TC（状态被重置？）"
    fi
else
    fault "LMS-API" "端口 $LMS_API_PORT /health 或 /status/main 不可达"
fi

# 2.2 深度健康指标（lms_ops_monitor.py 产出，5min 级）
LM_METRICS="$LMS_LOG_DIR/lms_metrics.jsonl"
LM_AGE=$(file_age "$LM_METRICS")
if [ "$LM_AGE" -lt 1800 ]; then
    ok "LMS-深度指标" "lms_metrics.jsonl $(age_label $LM_AGE)（深度健康检查活着）"
elif [ "$LM_AGE" -lt 7200 ]; then
    warn "LMS-深度指标" "lms_metrics.jsonl $(age_label $LM_AGE) 偏旧（深度健康检查 cron 可能停了）"
else
    fault "LMS-深度指标" "lms_metrics.jsonl $(age_label $LM_AGE) 停更——深度健康检查 cron 缺失/停止（历史上停过 22h）"
fi

# 2.3 告警账本（24h 内有 CRIT/WARN 提示留意）
LM_ALERTS="$LMS_LOG_DIR/lms_alerts.jsonl"
if [ -f "$LM_ALERTS" ]; then
    RECENT_ALERT=$(tail -30 "$LM_ALERTS" 2>/dev/null | python3 -c "
import json,sys,datetime
now=datetime.datetime.now().astimezone()
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    try: d=json.loads(line)
    except Exception: continue
    sev=d.get('severity') or d.get('level') or ''
    if sev not in ('CRIT','WARN'): continue
    ts=d.get('ts','')
    try:
        t=datetime.datetime.fromisoformat(ts.replace('Z','+00:00'))
        if (now-t).total_seconds() > 86400: continue  # 只看 24h 内
    except Exception:
        pass
    print('%s %s: %s' % (sev, ts, str(d.get('msg') or d.get('message') or '')[:80]))
" 2>/dev/null | tail -1)
    if [ -n "$RECENT_ALERT" ]; then
        warn "LMS-告警账本" "最近告警：$RECENT_ALERT"
    else
        ok "LMS-告警账本" "lms_alerts.jsonl 最近 30 条无 CRIT/WARN"
    fi
else
    warn "LMS-告警账本" "lms_alerts.jsonl 不存在"
fi

# 2.4 控制口 :8191
if ss -tln 2>/dev/null | grep -q ":$LMS_CONTROL_PORT "; then
    ok "LMS-控制口" "端口 $LMS_CONTROL_PORT 在听"
else
    warn "LMS-控制口" "端口 $LMS_CONTROL_PORT 未监听（控制指令不可达）"
fi

# =============================================================
# ③ 胶水层 glue（读侧融合）
# =============================================================
GLUE_HEALTH=$(http_get "http://127.0.0.1:$GLUE_PORT/health")
if [ -n "$GLUE_HEALTH" ]; then
    GLUE_INFO=$(echo "$GLUE_HEALTH" | python3 -c "
import json,sys
d=json.load(sys.stdin)
b=d.get('backends',{})
parts=[]
degraded=False
for k in ('sandglass','lms','vector'):
    v=b.get(k,{})
    h=v.get('healthy',False) if isinstance(v,dict) else False
    cnt=v.get('memory_count','') if isinstance(v,dict) else ''
    parts.append('%s=%s%s' % (k, '好' if h else '坏', ('('+str(cnt)+')') if cnt!='' else ''))
    if not h: degraded=True
print('%s|%s' % ('|'.join(parts), degraded))
" 2>/dev/null)
    if [ -n "$GLUE_INFO" ]; then
        GLUE_DETAIL=$(echo "$GLUE_INFO" | cut -d'|' -f1)
        GLUE_DEGRADED=$(echo "$GLUE_INFO" | cut -d'|' -f2)
        if [ "$GLUE_DEGRADED" = "True" ]; then
            fault "胶水层" "后端有坏：$GLUE_DETAIL"
        else
            ok "胶水层" "三后端全健康：$GLUE_DETAIL"
        fi
    else
        ok "胶水层" "health 可达（解析异常，原始: $(echo "$GLUE_HEALTH" | head -c 120)）"
    fi
else
    fault "胶水层" "端口 $GLUE_PORT /health 不可达（读侧断=AI 失忆）"
fi

# =============================================================
# ④ Agent OS 总线（调度器/消费者）
# =============================================================
EB="$ISO_SAND_HOME/data/event_bus.jsonl"
OP="$ISO_SAND_HOME/data/operation_log.jsonl"
DLQ="$ISO_SAND_HOME/data/.dead_letter_queue.jsonl"
EB_AGE=$(file_age "$EB"); OP_AGE=$(file_age "$OP")
SCH_PID=$(cat "$ISO_SAND_HOME/data/scheduler.pid" 2>/dev/null)
CON_PID=$(cat "$ISO_SAND_HOME/data/consumer.pid" 2>/dev/null)
SCH_OK="死"; CON_OK="死"
[ -n "$SCH_PID" ] && kill -0 "$SCH_PID" 2>/dev/null && SCH_OK="活($SCH_PID)"
[ -n "$CON_PID" ] && kill -0 "$CON_PID" 2>/dev/null && CON_OK="活($CON_PID)"
if [ "$EB_AGE" -lt 600 ] && [ "$OP_AGE" -lt 600 ] && [ "$SCH_OK" != "死" ] && [ "$CON_OK" != "死" ]; then
    DLQ_SIZE=$(stat -c %s "$DLQ" 2>/dev/null || echo 0)
    ok "总线" "event_bus $(age_label $EB_AGE) + operation_log $(age_label $OP_AGE)；scheduler$SCH_OK consumer$CON_OK；死信 ${DLQ_SIZE}B"
elif [ "$EB_AGE" -lt 1800 ] && [ "$OP_AGE" -lt 1800 ]; then
    warn "总线" "event_bus $(age_label $EB_AGE) / operation_log $(age_label $OP_AGE) 偏旧；scheduler$SCH_OK consumer$CON_OK"
else
    fault "总线" "event_bus $(age_label $EB_AGE) / operation_log $(age_label $OP_AGE) 停更——调度器或消费者死了（scheduler$SCH_OK consumer$CON_OK）"
fi

# =============================================================
# ⑤ 玄鉴 verify_daemon（审外监督）
# =============================================================
VD_PID=$(cat "$VERIFY_HOME/data/daemon.pid" 2>/dev/null)
VD_LOG="$VERIFY_HOME/data/daemon_audit.log"
VD_AGE=$(file_age "$VD_LOG")
VD_PID_OK="死"
[ -n "$VD_PID" ] && kill -0 "$VD_PID" 2>/dev/null && VD_PID_OK="活($VD_PID)"
if [ "$VD_AGE" -lt 600 ] && [ "$VD_PID_OK" != "死" ]; then
    ok "玄鉴-进程" "daemon$VD_PID_OK，audit 日志 $(age_label $VD_AGE)（5min 巡检活着）"
else
    fault "玄鉴-进程" "daemon$VD_PID_OK，audit 日志 $(age_label $VD_AGE) 停更——玄鉴死了"
fi
# 审计发现（近 200 行内 FAIL/WARN 计数）
VD_RECENT=$(tail -200 "$VD_LOG" 2>/dev/null | grep -c '"level": "FAIL"')
VD_RECENT_W=$(tail -200 "$VD_LOG" 2>/dev/null | grep -c '"level": "WARN"')
VD_SAMPLE=$(tail -200 "$VD_LOG" 2>/dev/null | grep '"level": "FAIL"' | tail -1 | python3 -c "import json,sys
line=sys.stdin.read().strip()
if not line: print('')
else:
    try:
        d=json.loads(line); print(str(d.get('detail',''))[:90])
    except Exception: print(line[:90])" 2>/dev/null)
if [ "${VD_RECENT:-0}" -eq 0 ]; then
    ok "玄鉴-审计发现" "近 200 行 0 FAIL / $VD_RECENT_W WARN（无异常发现）"
elif [ "$VD_RECENT" -le 5 ]; then
    warn "玄鉴-审计发现" "近 200 行 FAIL=$VD_RECENT WARN=$VD_RECENT_W（样例: $VD_SAMPLE）"
else
    fault "玄鉴-审计发现" "近 200 行 FAIL=$VD_RECENT WARN=$VD_RECENT_W（样例: $VD_SAMPLE）"
fi

# =============================================================
# ⑥ doubt-system 夜巡（每日 23:30 汇总怀疑）
# =============================================================
NP_MARKER="$WORKSPACE/logs/night_patrol.last_run"
if [ -f "$NP_MARKER" ]; then
    NP_DATE=$(cat "$NP_MARKER" 2>/dev/null)
    TODAY=$(date '+%Y-%m-%d'); YDAY=$(date -d yesterday '+%Y-%m-%d' 2>/dev/null || date -v-1d '+%Y-%m-%d' 2>/dev/null)
    if [ "$NP_DATE" = "$TODAY" ] || [ "$NP_DATE" = "$YDAY" ]; then
        ok "夜巡" "最近成功 $NP_DATE（每日 23:30 正常）"
    else
        fault "夜巡" "marker 停在 $NP_DATE——夜巡多日未成功（crontab 路径含空格被拆词，见文档）"
    fi
else
    fault "夜巡" "marker 不存在——夜巡从未成功跑过（crontab 行 'Agent OS' 空格未加引号；且脚本内 SCRIPTS 路径指向 workspace/scripts 找不到 night_patrol.py）"
fi

# =============================================================
# ⑦ self_pulse 唤醒链（每 10min）
# =============================================================
PULSE="/tmp/pulse-status.json"
P_AGE=$(file_age "$PULSE")
if [ -f "$PULSE" ]; then
    P_RC=$(python3 -c "import json;print(json.load(open('$PULSE')).get('pulse_rc','?'))" 2>/dev/null)
    P_ROUND=$(python3 -c "import json;d=json.load(open('$PULSE'));r=d.get('pulse_result',{});print(r.get('round','?') if isinstance(r,dict) else '?')" 2>/dev/null)
else
    P_RC="?"; P_ROUND="?"
fi
CHAIN_OK=1
for f in self_pulse_cli.py salience_gate.py sleep_pressure.py wake_client.py; do
    [ -f "$LIGHT_HOME/scripts/$f" ] || CHAIN_OK=0
done
if [ "$P_AGE" -lt 900 ] && [ "$P_RC" = "0" ] && [ "$CHAIN_OK" = "1" ]; then
    ok "self_pulse" "pulse-status $(age_label $P_AGE)，rc=$P_RC round=$P_ROUND，唤醒链 4 脚本齐"
elif [ "$P_AGE" -lt 1800 ]; then
    warn "self_pulse" "pulse-status $(age_label $P_AGE)，rc=$P_RC（cron */10 可能延迟或脚本报错）"
else
    fault "self_pulse" "pulse-status $(age_label $P_AGE) 停更——唤醒链断（pulse-cron.sh cron 缺失？）"
fi

# =============================================================
# ⑧ OpenClaw 插件 glue-memory-injector（读侧回魂）
# =============================================================
HOOK="/tmp/glue-hook-debug.log"
H_AGE=$(file_age "$HOOK")
if [ -f "$HOOK" ] && [ "$H_AGE" -lt 604800 ]; then
    H_LAST=$(tail -1 "$HOOK" 2>/dev/null | head -c 80)
    ok "回魂插件" "glue-hook-debug.log $(age_label $H_AGE) 有注入（最近: $H_LAST）"
elif [ -f "$HOOK" ]; then
    warn "回魂插件" "glue-hook-debug.log $(age_label $H_AGE) 很久没注入（一周无对话？）"
else
    warn "回魂插件" "glue-hook-debug.log 不存在——插件可能没启用"
fi

# =============================================================
# ⑨ 备份（15min/小时/每日 三档）
# =============================================================
BK_LOG="$LMS_LOG_DIR/lms_backup_cron.log"
if [ -f "$BK_LOG" ]; then
    BK_ERR_NOW=$(tail -40 "$BK_LOG" 2>/dev/null | grep -cE "ERROR|失败|rc=[^0]")
    BK_ERR_DAY=$(grep "$(date '+%Y-%m-%d')" "$BK_LOG" 2>/dev/null | grep -cE "ERROR|失败|rc=[^0]")
else
    BK_ERR_NOW=0; BK_ERR_DAY=0
fi
BK_NEWEST=$(ls -t "$BACKUP_ROOT/snapshots-15min/" 2>/dev/null | head -1)
BK_AGE=$(file_age "$BACKUP_ROOT/snapshots-15min/$BK_NEWEST" 2>/dev/null)
if [ "$BK_ERR_NOW" -eq 0 ] && [ "$BK_AGE" -lt 1800 ]; then
    ok "备份" "cron 日志无近期 ERROR，最新快照 $(age_label $BK_AGE)（$BK_NEWEST）"
elif [ "$BK_ERR_NOW" -eq 0 ] && [ "$BK_AGE" -lt 7200 ]; then
    warn "备份" "快照 $(age_label $BK_AGE) 偏旧（--quick 每 15min 应更新）"
else
    fault "备份" "快照 $(age_label $BK_AGE)；今日 ERROR=$BK_ERR_DAY 次（最近: $BK_ERR_NOW）——看 $LMS_LOG_DIR/lms_backup.log"
fi

# =============================================================
# ⑩ cron 完整性（怀疑三把锁 + 备份 + 深度健康 + 巡检自身）
# =============================================================
CRON=$(crontab -l 2>/dev/null)
MISSING=""
for key in "pulse-cron.sh" "night_patrol_run.sh" "lms_backup.sh" "session-reset-watchdog" "health-check.sh" "lms_ops_monitor.py" "system_health_check.sh"; do
    echo "$CRON" | grep -qF "$key" || MISSING="$MISSING $key"
done
if [ -z "$MISSING" ]; then
    ok "cron完整性" "怀疑三把锁+备份+深度健康+巡检 全部在位"
else
    warn "cron完整性" "crontab 缺失:$MISSING"
fi

# =============================================================
# ⑪ 磁盘水位（只读 df）
# =============================================================
VOL2_USE=$(df -P /vol2 2>/dev/null | awk 'NR==2 {gsub("%","",$5); print $5}')
if [ -n "${VOL2_USE:-}" ]; then
    if [ "$VOL2_USE" -ge 95 ]; then
        fault "磁盘" "/vol2 使用率 ${VOL2_USE}%"
    elif [ "$VOL2_USE" -ge 90 ]; then
        warn "磁盘" "/vol2 使用率 ${VOL2_USE}%"
    else
        ok "磁盘" "/vol2 使用率 ${VOL2_USE}%"
    fi
else
    ok "磁盘" "/vol2 df 不可读，跳过"
fi

# =============================================================
# 汇总与输出
# =============================================================
VERDICT_OK=0; VERDICT_WARN=0; VERDICT_FAULT=0
echo ""
echo "===== Agent OS 全系统健康巡检 · $NOW_ISO ====="
echo ""
printf "%-16s %-6s %s\n" "组件" "状态" "证据与判定依据"
printf -- "--------------------------------------------------------\n"
TABLE=""
while IFS='|' read -r name st detail; do
    [ -z "$name" ] && continue
    case "$st" in
        OK)   VERDICT_OK=$((VERDICT_OK+1));;
        WARN) VERDICT_WARN=$((VERDICT_WARN+1));;
        FAULT) VERDICT_FAULT=$((VERDICT_FAULT+1));;
    esac
    printf "%s %-14s %-6s %s\n" "$(emoji "$st")" "$name" "$st" "$detail"
    TABLE="$TABLE$name|$st|$detail\n"
done < "$RES"
echo ""
echo "===== 汇总表 ====="
printf "%-16s %-6s %s\n" "组件" "状态" "关键数字"
printf -- "--------------------------------------------------------\n"
while IFS='|' read -r name st detail; do
    [ -z "$name" ] && continue
    printf "%-16s %-6s %s\n" "$name" "$st" "$detail"
done < "$RES"
echo ""
echo "结果: 绿=$VERDICT_OK 黄=$VERDICT_WARN 红=$VERDICT_FAULT"
if [ "$VERDICT_FAULT" -gt 0 ]; then
    echo "判定: ❌ 有故障（exit 2）——见上方红色项，逐项查 SYSTEM_HEALTH.md「故障了怎么办」"
    EXIT_CODE=2
elif [ "$VERDICT_WARN" -gt 0 ]; then
    echo "判定: ⚠️ 有警告（exit 1）"
    EXIT_CODE=1
else
    echo "判定: ✅ 全绿（exit 0）"
    EXIT_CODE=0
fi

# ---------- cron 模式：追加日志 + 状态变化告警 ----------
if [ "$MODE" = "--cron" ]; then
    mkdir -p "$LOG_DIR"
    {
        echo ""
        echo "########## $NOW_ISO 系统健康巡检 (cron) ##########"
        echo "结果: 绿=$VERDICT_OK 黄=$VERDICT_WARN 红=$VERDICT_FAULT exit=$EXIT_CODE"
        printf "%-16s %-6s %s\n" "组件" "状态" "证据"
        printf -- "--------------------------------------------------------\n"
        while IFS='|' read -r name st detail; do
            [ -z "$name" ] && continue
            printf "%s %-14s %-6s %s\n" "$(emoji "$st")" "$name" "$st" "$detail"
        done < "$RES"
    } >> "$HL_LOG"

    # 与上次状态比对（首次运行=建基线，不告警）
    NEW_STATE=$(mktemp)
    while IFS='|' read -r name st detail; do
        [ -z "$name" ] && continue
        printf '%s|%s|%s\n' "$name" "$st" "$detail" >> "$NEW_STATE"
    done < "$RES"

    while IFS='|' read -r name st detail; do
        [ -z "$name" ] && continue
        OLD=$(grep -F "$name|" "$STATE_FILE" 2>/dev/null | tail -1)
        OLD_ST=$(echo "$OLD" | cut -d'|' -f2)
        if [ -z "$OLD_ST" ]; then
            continue  # 首次出现：只记录基线
        fi
        if [ "$st" != "$OLD_ST" ]; then
            TS=$(date '+%F %T')
            if [ "$st" = "OK" ]; then
                echo "✅ [$TS] [$name] 恢复: $detail" >> "$HL_LOG"
            elif [ "$OLD_ST" = "OK" ]; then
                echo "🚨 [$TS] [$name] 故障: $detail" >> "$HL_LOG"
            else
                # 黄→红 或 红→黄：都算状态恶化/好转，按新状态打标
                if [ "$st" = "FAULT" ]; then
                    echo "🚨 [$TS] [$name] 升级为故障: $detail" >> "$HL_LOG"
                else
                    echo "⚠️ [$TS] [$name] 降为警告: $detail" >> "$HL_LOG"
                fi
            fi
        fi
    done < "$NEW_STATE"

    # 轮次记录（LMS 回退检测用）
    TC_NOW=$(grep '^LMS-API|OK\|^LMS-API|WARN' "$NEW_STATE" 2>/dev/null | tail -1 | grep -oE '轮次=[0-9]+' | cut -d= -f2)
    cp "$NEW_STATE" "$STATE_FILE"
    rm -f "$NEW_STATE"
    # 状态文件清理（保留 400 行以内）
    tail -400 "$STATE_FILE" > "$STATE_FILE.tmp" 2>/dev/null && mv "$STATE_FILE.tmp" "$STATE_FILE" 2>/dev/null
    echo "[$(date '+%F %T')] 巡检完成，状态文件已更新: $STATE_FILE" >> "$HL_LOG"
fi

rm -f "$RES"
exit "$EXIT_CODE"
