#!/bin/bash
# =============================================================
# Agent OS 一键停止（Phase 6 部署一致性）
# 按逆序停止：verify_daemon → iso-sand → glue_server → LMS → 沙漏
# 用 PID 文件精确 kill；停止后确认端口释放
# 用法: bash stop_all.sh
# =============================================================
set -u

AGENT_OS_HOME="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$AGENT_OS_HOME/env.local" ]; then
    set -a; . "$AGENT_OS_HOME/env.local"; set +a
fi
RUN_DIR="${RUN_DIR:-$AGENT_OS_HOME/run}"
ISO_SAND_HOME="${ISO_SAND_HOME:-$AGENT_OS_HOME/iso-sand}"
VERIFY_HOME="${VERIFY_HOME:-$AGENT_OS_HOME/../AgentOS-IsoSand/同构沙盘}"
SANDGLASS_API_PORT="${SANDGLASS_API_PORT:-17333}"
LMS_API_PORT="${LMS_API_PORT:-8190}"
GLUE_PORT="${GLUE_PORT:-19000}"

stop_by_pidfile() {
    local name="$1" pidfile="$2" port="$3"
    local PID=""
    # 端口服务：优先按端口解析真实 PID（setsid 可能 fork，pidfile 可能是父进程）
    if [ -n "$port" ]; then
        PID=$(ss -tlnp 2>/dev/null | grep ":$port " | grep -oP 'pid=\K[0-9]+' | head -1)
    fi
    if [ -z "$PID" ] && [ -f "$pidfile" ]; then
        PID=$(cat "$pidfile")
    fi
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null && echo "  ⏹️  $name (PID $PID)" || echo "  ⚠️  $name kill 失败"
    else
        echo "  ⏭️  $name 未在运行"
    fi
    rm -f "$pidfile"
}

echo "=== Agent OS 一键停止 ($(date '+%F %T')) ==="

# 5. 玄鉴 verify_daemon
echo "--- [5/5→1/5] 逆序停止 ---"
stop_by_pidfile "verify_daemon" "$RUN_DIR/verify_daemon.pid" ""
# 玄鉴自身也有 daemon.pid（同构沙盘 data/），一并清理
VDPID=$(cat "$VERIFY_HOME/data/daemon.pid" 2>/dev/null)
if [ -n "$VDPID" ] && kill -0 "$VDPID" 2>/dev/null; then
    kill "$VDPID" 2>/dev/null && echo "  ⏹️  verify_daemon (data/daemon.pid $VDPID)"
fi

# 4. iso-sand（scheduler + consumer，用其自带 stop_all）
echo "--- iso-sand ---"
bash "$ISO_SAND_HOME/stop_all.sh"

# 3. 胶水层 glue_server (19000)
stop_by_pidfile "glue_server" "$RUN_DIR/glue_server.pid" "$GLUE_PORT"

# 2. LMS API (8190)
stop_by_pidfile "lms_api" "$RUN_DIR/lms_api.pid" "$LMS_API_PORT"

# 1. 沙漏 HTTP API (17333)
stop_by_pidfile "sandglass_http_api" "$RUN_DIR/sandglass_http_api.pid" "$SANDGLASS_API_PORT"

sleep 2
echo ""
echo "=== 端口释放确认 ==="
for PORT in "$SANDGLASS_API_PORT" "$LMS_API_PORT" "$GLUE_PORT"; do
    if ss -tln 2>/dev/null | grep -q ":$PORT "; then
        echo "  ❌ 端口 $PORT 仍被占用: $(ss -tlnp 2>/dev/null | grep ":$PORT " | head -1)"
    else
        echo "  ✅ 端口 $PORT 已释放"
    fi
done

echo "=== ✅ Agent OS 已停止 ==="
