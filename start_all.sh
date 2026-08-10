#!/bin/bash
# =============================================================
# Agent OS 一键启动（Phase 6 部署一致性）
# 按依赖顺序启动全部服务：沙漏 17333 → LMS 8190 → 胶水层 19000
#   → iso-sand scheduler/consumer → verify_daemon
# 每个服务：setsid 独立进程 + 日志 + PID 文件 + 启动后 health 检查
# 用法: bash start_all.sh
# =============================================================
set -u

AGENT_OS_HOME="$(cd "$(dirname "$0")" && pwd)"
# 加载 env.local（配置中心；缺失时用相对路径推导，绝不硬编码绝对路径）
if [ -f "$AGENT_OS_HOME/env.local" ]; then
    set -a; . "$AGENT_OS_HOME/env.local"; set +a
fi
# 相对推导默认值（以 AGENT_OS_HOME 为锚点，标准布局下自动定位）
NEXSANDBASE_HOME="${NEXSANDBASE_HOME:-$AGENT_OS_HOME/../所有自动化/轻如烟/sandglass}"
SANDGLASS_SOURCE="${SANDGLASS_SOURCE:-$AGENT_OS_HOME/../所有自动化/轻如烟/sandglass_source}"
SANDGLASS_API_PORT="${SANDGLASS_API_PORT:-17333}"
LMS_HOME="${LMS_HOME:-$AGENT_OS_HOME/../living-memory-system-cloud}"
LMS_API_PORT="${LMS_API_PORT:-8190}"
GLUE_HOME="${GLUE_HOME:-$AGENT_OS_HOME/../memory-integration-layer}"
GLUE_PORT="${GLUE_PORT:-19000}"
ISO_SAND_HOME="${ISO_SAND_HOME:-$AGENT_OS_HOME/iso-sand}"
VERIFY_HOME="${VERIFY_HOME:-$AGENT_OS_HOME/../AgentOS-IsoSand/同构沙盘}"
RUN_DIR="${RUN_DIR:-$AGENT_OS_HOME/run}"
LOG_DIR="${LOG_DIR:-$AGENT_OS_HOME/logs}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

FAILED=0
note_ok()   { echo "  ✅ $1"; }
note_fail() { echo "  ❌ $1"; FAILED=1; }

echo "=== Agent OS 一键启动 ($(date '+%F %T')) ==="
echo "配置源: $([ -f "$AGENT_OS_HOME/env.local" ] && echo env.local || echo 内置默认值)"

# ── 1. 沙漏 HTTP API (17333) ─────────────────────────────────
echo "--- [1/5] 沙漏 HTTP API (端口 $SANDGLASS_API_PORT) ---"
PID_FILE="$RUN_DIR/sandglass_http_api.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    note_ok "已在运行 PID=$(cat "$PID_FILE")，跳过"
else
    ( cd "$SANDGLASS_SOURCE" && \
      NEXSANDBASE_HOME="$NEXSANDBASE_HOME" SANDGLASS_SOURCE="$SANDGLASS_SOURCE" \
      setsid python3 sandglass_http_api.py > "$LOG_DIR/sandglass_http_api.log" 2>&1 < /dev/null & echo $! > "$PID_FILE" )
    sleep 2
    if curl -sf "http://127.0.0.1:$SANDGLASS_API_PORT/api/health" > /dev/null 2>&1; then
        # setsid 可能 fork，按端口解析真实 PID
        REAL_PID=$(ss -tlnp 2>/dev/null | grep ":$SANDGLASS_API_PORT " | grep -oP 'pid=\K[0-9]+' | head -1)
        [ -n "$REAL_PID" ] && echo "$REAL_PID" > "$PID_FILE"
        note_ok "health OK（PID=${REAL_PID:-$(cat "$PID_FILE")}）"
    else
        note_fail "health 失败，日志: $LOG_DIR/sandglass_http_api.log"
    fi
fi

# ── 2. LMS API (8190) ────────────────────────────────────────
echo "--- [2/5] 活体记忆 LMS API (端口 $LMS_API_PORT) ---"
PID_FILE="$RUN_DIR/lms_api.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    note_ok "已在运行 PID=$(cat "$PID_FILE")，跳过"
else
    if [ ! -f "$LMS_HOME/.env" ]; then
        note_fail "缺少 $LMS_HOME/.env（含密钥与嵌入配置），无法启动 LMS"
    else
        ( cd "$LMS_HOME" && set -a && . "$LMS_HOME/.env" && set +a && \
          setsid "$LMS_HOME/.venv/bin/python" -m api.run --host 127.0.0.1 --port "$LMS_API_PORT" \
          > "$LOG_DIR/lms_api.log" 2>&1 < /dev/null & echo $! > "$PID_FILE" )
        # LMS 启动慢（嵌入模型初始化），轮询等待 health（最长 40s）
        LMS_OK=0
        for i in $(seq 1 13); do
            sleep 3
            if curl -sf "http://127.0.0.1:$LMS_API_PORT/health" > /dev/null 2>&1; then LMS_OK=1; break; fi
        done
        if [ "$LMS_OK" -eq 1 ]; then
            REAL_PID=$(ss -tlnp 2>/dev/null | grep ":$LMS_API_PORT " | grep -oP 'pid=\K[0-9]+' | head -1)
            [ -n "$REAL_PID" ] && echo "$REAL_PID" > "$PID_FILE"
            note_ok "health OK（PID=${REAL_PID:-$(cat "$PID_FILE")}）"
        else
            note_fail "health 失败（40s 超时），日志: $LOG_DIR/lms_api.log"
        fi
    fi
fi

# ── 3. 胶水层 glue_server (19000) ────────────────────────────
echo "--- [3/5] 胶水层 glue_server (端口 $GLUE_PORT) ---"
PID_FILE="$RUN_DIR/glue_server.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    note_ok "已在运行 PID=$(cat "$PID_FILE")，跳过"
else
    ( cd "$GLUE_HOME" && \
      setsid python3 glue_server.py --host 127.0.0.1 --port "$GLUE_PORT" \
      > "$LOG_DIR/glue_server.log" 2>&1 < /dev/null & echo $! > "$PID_FILE" )
    sleep 3
    if curl -sf "http://127.0.0.1:$GLUE_PORT/health" > /dev/null 2>&1; then
        REAL_PID=$(ss -tlnp 2>/dev/null | grep ":$GLUE_PORT " | grep -oP 'pid=\K[0-9]+' | head -1)
        [ -n "$REAL_PID" ] && echo "$REAL_PID" > "$PID_FILE"
        note_ok "health OK（PID=${REAL_PID:-$(cat "$PID_FILE")}）"
    else
        note_fail "health 失败，日志: $LOG_DIR/glue_server.log"
    fi
fi

# ── 4. iso-sand 事件总线（scheduler + consumer）──────────────
echo "--- [4/5] iso-sand 调度器 + 消费者 ---"
# setsid 包裹：即使启动脚本被中断，调度器/消费者也独立成会话存活
setsid bash "$ISO_SAND_HOME/start_scheduler.sh"
setsid bash "$ISO_SAND_HOME/start_consumer.sh"
sleep 2
S_PID=$(cat "$ISO_SAND_HOME/data/scheduler.pid" 2>/dev/null)
C_PID=$(cat "$ISO_SAND_HOME/data/consumer.pid" 2>/dev/null)
if kill -0 "$S_PID" 2>/dev/null && kill -0 "$C_PID" 2>/dev/null; then
    note_ok "scheduler PID=$S_PID, consumer PID=$C_PID"
else
    note_fail "scheduler/consumer 未全部存活（scheduler=$S_PID consumer=$C_PID）"
fi

# ── 5. 玄鉴 verify_daemon ────────────────────────────────────
echo "--- [5/5] 玄鉴 verify_daemon ---"
PID_FILE="$RUN_DIR/verify_daemon.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    note_ok "已在运行 PID=$(cat "$PID_FILE")，跳过"
else
    ( cd "$VERIFY_HOME" && \
      setsid python3 src/verify_daemon.py > "$LOG_DIR/verify_daemon.log" 2>&1 < /dev/null & echo $! > "$PID_FILE" )
    sleep 3
    if [ -f "$VERIFY_HOME/data/daemon.pid" ] && kill -0 "$(cat "$VERIFY_HOME/data/daemon.pid")" 2>/dev/null; then
        # 玄鉴自写 daemon.pid 是真实 PID，同步到 run/
        cp "$VERIFY_HOME/data/daemon.pid" "$PID_FILE"
        note_ok "运行中 PID=$(cat "$VERIFY_HOME/data/daemon.pid")"
    else
        note_fail "verify_daemon 未存活，日志: $LOG_DIR/verify_daemon.log"
    fi
fi

echo ""
if [ "$FAILED" -eq 0 ]; then
    echo "=== ✅ 全部服务启动完成 ==="
else
    echo "=== ⚠️ 存在失败项，请用 status_all.sh 复查 ==="
fi

# ── 怀疑钩子：部署后自动怀疑（doubt_hook.py，fail-open 不阻断）──
# 每次全栈启动后生成一条 novelty 怀疑：本次部署是否正确？喂 LMS 塑形 + 账本留痕
if [ -f "$AGENT_OS_HOME/doubt-system/doubt_hook.py" ]; then
    DOUBT_MSG="start_all.sh 全栈启动 $(date '+%F %T')"
    if [ "$FAILED" -eq 0 ]; then
        python3 "$AGENT_OS_HOME/doubt-system/doubt_hook.py" --deploy "$DOUBT_MSG" --health "http://127.0.0.1:${LMS_API_PORT:-8190}/health" --topic deploy-start-all --quiet 2>/dev/null || true
    else
        python3 "$AGENT_OS_HOME/doubt-system/doubt_hook.py" --fail "start_all.sh 存在失败项: $DOUBT_MSG" --topic deploy-start-all --quiet 2>/dev/null || true
    fi
fi
exit $FAILED
