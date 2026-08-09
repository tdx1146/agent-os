#!/bin/bash
# =============================================================
# Agent OS 一键状态（Phase 6 部署一致性）
# 查所有服务：进程 + 端口 + health 端点
# 用法: bash status_all.sh
# =============================================================
set -u

AGENT_OS_HOME="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$AGENT_OS_HOME/env.local" ]; then
    set -a; . "$AGENT_OS_HOME/env.local"; set +a
fi
SANDGLASS_API_PORT="${SANDGLASS_API_PORT:-17333}"
LMS_API_PORT="${LMS_API_PORT:-8190}"
GLUE_PORT="${GLUE_PORT:-19000}"
ISO_SAND_HOME="${ISO_SAND_HOME:-$AGENT_OS_HOME/iso-sand}"
VERIFY_HOME="${VERIFY_HOME:-$AGENT_OS_HOME/../AgentOS-IsoSand/同构沙盘}"
RUN_DIR="${RUN_DIR:-$AGENT_OS_HOME/run}"

check() { # name, pid, port, health_url
    local name="$1" pid="$2" port="$3" url="$4"
    local p_ok="❌" h_ok="❌"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && p_ok="✅"
    if [ -n "$port" ]; then
        ss -tln 2>/dev/null | grep -q ":$port " && port_ok="✅" || port_ok="❌"
    else
        port_ok="—"
    fi
    if [ -n "$url" ]; then
        curl -sf --max-time 5 "$url" > /dev/null 2>&1 && h_ok="✅"
    else
        h_ok="—"
    fi
    printf "  %-18s 进程:%s 端口:%s health:%s  (PID=%s)\n" "$name" "$p_ok" "$port_ok" "$h_ok" "${pid:-无}"
}

echo "=== Agent OS 服务状态 ($(date '+%F %T')) ==="
check "sandglass_api"   "$(cat "$RUN_DIR/sandglass_http_api.pid" 2>/dev/null)" "$SANDGLASS_API_PORT" "http://127.0.0.1:$SANDGLASS_API_PORT/api/health"
check "lms_api"         "$(cat "$RUN_DIR/lms_api.pid" 2>/dev/null)"               "$LMS_API_PORT"      "http://127.0.0.1:$LMS_API_PORT/health"
check "glue_server"     "$(cat "$RUN_DIR/glue_server.pid" 2>/dev/null)"           "$GLUE_PORT"         "http://127.0.0.1:$GLUE_PORT/health"
check "scheduler"       "$(cat "$ISO_SAND_HOME/data/scheduler.pid" 2>/dev/null)"  ""                   ""
check "consumer"        "$(cat "$ISO_SAND_HOME/data/consumer.pid" 2>/dev/null)"   ""                   ""
check "verify_daemon"   "$(cat "$VERIFY_HOME/data/daemon.pid" 2>/dev/null)"       ""                   ""

echo ""
echo "=== 关键数据点 ==="
curl -s --max-time 5 "http://127.0.0.1:$SANDGLASS_API_PORT/api/health" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print('  沙漏 sandglass_count:', d.get('sandglass_count'))" 2>/dev/null || echo "  沙漏 API 不可达"
curl -s --max-time 5 "http://127.0.0.1:$GLUE_PORT/health" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print('  胶水层 backends:', json.dumps(d.get('backends',{}), ensure_ascii=False))" 2>/dev/null || echo "  胶水层不可达"
echo "  玄鉴 audit 最近: $(tail -1 "$VERIFY_HOME/data/daemon_audit.log" 2>/dev/null | head -c 120 || echo 无)"
echo "=== 完 ==="
