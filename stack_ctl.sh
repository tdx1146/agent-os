#!/bin/bash
# =============================================================
# stack_ctl.sh — 轻如烟体系统一服务管理器（工程化入口）
# -------------------------------------------------------------
# 一个入口管理全部常驻服务，部署者无需记忆各服务的启动命令。
#   表驱动：新增服务只需在 SERVICES 清单加一行。
#   命令：setup | doctor | start | stop | restart | status | health | logs | list
#   示例：
#     ./stack_ctl.sh setup                 # 首次部署向导（生成+校验配置）
#     ./stack_ctl.sh doctor                # 全配置体检（路径/端口/依赖命令）
#     ./stack_ctl.sh status                # 全部服务状态一览
#     ./stack_ctl.sh start                 # 按依赖顺序启动全部（幂等）
#     ./stack_ctl.sh restart lms-api       # 重启单个服务
#     ./stack_ctl.sh health                # 深度健康检查（含等待）
#     ./stack_ctl.sh logs glue             # 跟随某服务日志
#  设计要点：
#    - 零硬编码：绝对路径只来自 env.local（配置中心），缺失时相对推导
#    - 幂等：已在跑（端口健康）的服务跳过，不重复启动
#    - 依赖：按 depends 拓扑顺序启动 / 逆序停止
#    - 优雅停机：SIGTERM → 等待 → 仍存活才 SIGKILL
#    - PID 解析：按端口解析真实 PID（setsid fork 后可靠）
# =============================================================
set -u

# ---------- 配置加载（唯一来源：env.local，缺失时相对推导，绝不硬编码） ----------
AGENT_OS_HOME="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$AGENT_OS_HOME/env.local" ]; then
    set -a; . "$AGENT_OS_HOME/env.local"; set +a
fi
ISO_SAND_HOME="${ISO_SAND_HOME:-$AGENT_OS_HOME/iso-sand}"
RUN_DIR="${RUN_DIR:-$AGENT_OS_HOME/run}"
LOG_DIR="${LOG_DIR:-$AGENT_OS_HOME/logs}"
SANDGLASS_API_PORT="${SANDGLASS_API_PORT:-17333}"
LMS_API_PORT="${LMS_API_PORT:-8190}"
GLUE_PORT="${GLUE_PORT:-19000}"

CMD="${1:-status}"

# 外部仓库路径：env.local 缺失时给出明确指引（setup/doctor 例外，它们负责引导）
if [ "$CMD" != "setup" ] && [ "$CMD" != "doctor" ]; then
    for v in LMS_HOME GLUE_HOME SANDGLASS_SOURCE NEXSANDBASE_HOME VERIFY_HOME; do
        if [ -z "${!v:-}" ]; then
            echo "❌ 缺少配置 $v（$AGENT_OS_HOME/env.local 缺失或未定义该变量）" >&2
            echo "   请先运行: ./stack_ctl.sh setup  （首次部署向导）" >&2
            exit 1
        fi
    done
fi

mkdir -p "$RUN_DIR" "$LOG_DIR"

# ---------- 服务清单（表驱动，| 分隔） ----------
# 字段：name | cwd | cmd | env_file(空=无) | port(空=无) | health_url(空=跳过) | depends(逗号分隔) | 说明
SERVICES=(
  "sandglass|$SANDGLASS_SOURCE|python3 sandglass_http_api.py||$SANDGLASS_API_PORT|/api/health||沙漏状态中枢"
  "lms-api|$LMS_HOME|.venv/bin/python -m api.run --host 127.0.0.1 --port $LMS_API_PORT|.env|$LMS_API_PORT|/health|sandglass|活体记忆系统(生命)"
  "glue|$GLUE_HOME|python3 glue_server.py --host 127.0.0.1 --port $GLUE_PORT||$GLUE_PORT|/health|lms-api|胶水层(记忆注入/落沙)"
  "scheduler|$ISO_SAND_HOME|bash start_scheduler.sh|||event_bus 流动检查|glue|总线调度器"
  "consumer|$ISO_SAND_HOME|bash start_consumer.sh||||scheduler|总线消费者(含LMS停喂过滤)"
  "verify|$VERIFY_HOME|python3 src/verify_daemon.py|||data/daemon.pid 存活|consumer|玄鉴5min巡检"
)

C_GREEN='\033[0;32m'; C_RED='\033[0;31m'; C_YEL='\033[1;33m'; C_DIM='\033[2m'; C_RST='\033[0m'

# ---------- 工具函数 ----------
ok()   { echo -e "${C_GREEN}✅ $1${C_RST}"; }
fail() { echo -e "${C_RED}❌ $1${C_RST}"; }
warn() { echo -e "${C_YEL}⚠️  $1${C_RST}"; }
dim()  { echo -e "${C_DIM}$1${C_RST}"; }

# 按端口解析真实 PID（优先于 PID 文件，setsid fork 后可靠）
pid_by_port() {
  local port="$1"
  [ -z "$port" ] && return 1
  ss -tlnp 2>/dev/null | grep ":$port " | grep -oP 'pid=\K[0-9]+' | head -1
}

# 服务健康探测：HTTP 端点 or 进程存活
svc_healthy() {  # name cwd cmd env_file port health_url depends desc
  local name="$1" cwd="$2" cmd="$3" envf="$4" port="$5" health="$6"
  if [ -n "$port" ]; then
    local pid; pid=$(pid_by_port "$port")
    [ -z "$pid" ] && return 1
    if [ -n "$health" ]; then
      curl -sf -m 3 "http://127.0.0.1:${port}${health}" > /dev/null 2>&1
      return $?
    fi
    kill -0 "$pid" 2>/dev/null; return $?
  else
    # 无端口服务：优先 PID 文件；scheduler/consumer 用 iso-sand/data/*.pid；
    # 最后按 cmdline 兜底（start_*.sh 内部 exec 到 .run_*.py）
    local pidfile="$RUN_DIR/${name}.pid"
    [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null && return 0
    local alt_pidfile="$ISO_SAND_HOME/data/${name}.pid"
    [ -f "$alt_pidfile" ] && kill -0 "$(cat "$alt_pidfile")" 2>/dev/null && return 0
    local pat
    case "$name" in
      scheduler) pat=".run_scheduler" ;;
      consumer)  pat=".run_consumer"  ;;
      *)         pat="$(echo "$cmd" | awk '{print $NF}')" ;;
    esac
    pgrep -f "$pat" > /dev/null 2>&1 && return 0
    return 1
  fi
}

# 启动单个服务（幂等）
svc_start() {  # name cwd cmd env_file port health_url depends desc
  local name="$1" cwd="$2" cmd="$3" envf="$4" port="$5" health="$6" deps="$7" desc="$8"
  if svc_healthy "$@"; then
    ok "$name 已在运行（${desc}）"
    return 0
  fi
  [ -n "$deps" ] && for d in ${deps//,/ }; do
    dep_line=""
    for ds in "${SERVICES[@]}"; do
      IFS='|' read -r dn dc dcmd denvf dport dhealth ddeps ddesc <<< "$ds"
      [ "$dn" = "$d" ] && dep_line="$ds" && break
    done
    if [ -n "$dep_line" ]; then
      IFS='|' read -r dn dc dcmd denvf dport dhealth ddeps ddesc <<< "$dep_line"
      if ! svc_healthy "$dn" "$dc" "$dcmd" "$denvf" "$dport" "$dhealth" "$ddeps" "$ddesc"; then
        fail "$name 依赖 $d 未就绪，跳过（请先启动 $d）"
        return 1
      fi
    fi
  done
  echo -e "  → 启动 $name（$desc）..."
  local logfile="$LOG_DIR/${name}.log"
  ( cd "$cwd" || return 1
    [ -n "$envf" ] && { set -a; . "./$envf" 2>/dev/null; set +a; }
    export NEXSANDBASE_HOME="$NEXSANDBASE_HOME"
    setsid bash -c "$cmd" > "$logfile" 2>&1 < /dev/null &
    echo $! > "$RUN_DIR/${name}.pid" )
  # 等待健康（LMS 启动慢，最长 45s；其余 8s）
  local wait_max=8; [ "$name" = "lms-api" ] && wait_max=45
  for i in $(seq 1 $((wait_max / 2))); do
    sleep 2
    svc_healthy "$@" && { ok "$name 就绪（PID=$(pid_by_port "$port" 2>/dev/null || cat "$RUN_DIR/${name}.pid")）"; return 0; }
  done
  fail "$name 启动超时，日志: $logfile（tail）"
  tail -5 "$logfile" 2>/dev/null | sed 's/^/    /'
  return 1
}

# 停止单个服务（优雅：SIGTERM → 等待 → SIGKILL）
svc_stop() {  # name cwd cmd env_file port health_url depends desc
  local name="$1" port="$5"
  local pid; pid=$(pid_by_port "$port" 2>/dev/null)
  if [ -z "$pid" ] && [ -f "$RUN_DIR/${name}.pid" ]; then
    pid=$(cat "$RUN_DIR/${name}.pid"); kill -0 "$pid" 2>/dev/null || pid=""
  fi
  if [ -z "$pid" ]; then
    dim "  $name 未在运行，跳过"
    return 0
  fi
  echo -e "  → 停止 $name（PID=$pid）..."
  kill "$pid" 2>/dev/null
  for i in $(seq 1 15); do  # 最长 30s 优雅窗口（LMS 需落盘）
    kill -0 "$pid" 2>/dev/null || { ok "$name 已优雅停止"; return 0; }
    sleep 2
  done
  kill -9 "$pid" 2>/dev/null && warn "$name 优雅超时，已强杀"
  rm -f "$RUN_DIR/${name}.pid"
}

# ---------- 部署向导 / 配置体检 ----------
# doctor_run <env文件>：全配置校验（配置文件/必需变量/路径/端口/依赖命令）
doctor_run() {
  local envf="$1" rc=0 v port listener c
  echo "── [1/5] 配置文件 ──"
  if [ -f "$envf" ]; then
    ok "env.local 存在: $envf"
  else
    fail "env.local 缺失（请先运行 ./stack_ctl.sh setup 生成）"; return 1
  fi
  set -a; . "$envf"; set +a
  # 相对推导兜底（与主入口一致）
  ISO_SAND_HOME="${ISO_SAND_HOME:-$AGENT_OS_HOME/iso-sand}"
  RUN_DIR="${RUN_DIR:-$AGENT_OS_HOME/run}"
  LOG_DIR="${LOG_DIR:-$AGENT_OS_HOME/logs}"
  SANDGLASS_API_PORT="${SANDGLASS_API_PORT:-17333}"
  LMS_API_PORT="${LMS_API_PORT:-8190}"
  GLUE_PORT="${GLUE_PORT:-19000}"
  EDITOR_PORT="${EDITOR_PORT:-18888}"

  echo "── [2/5] 必需变量 ──"
  for v in AGENT_OS_HOME LIGHT_HOME LMS_HOME GLUE_HOME VERIFY_HOME SANDGLASS_SOURCE NEXSANDBASE_HOME ISO_SAND_HOME RUN_DIR LOG_DIR SANDGLASS_API_PORT LMS_API_PORT GLUE_PORT; do
    if [ -z "${!v:-}" ]; then
      fail "变量 $v 未定义"; rc=1
    else
      ok "变量 $v = ${!v}"
    fi
  done

  echo "── [3/5] 路径存在性 ──"
  for v in AGENT_OS_HOME LIGHT_HOME LMS_HOME GLUE_HOME VERIFY_HOME SANDGLASS_SOURCE NEXSANDBASE_HOME ISO_SAND_HOME RUN_DIR LOG_DIR; do
    if [ -d "${!v}" ]; then
      ok "目录 $v → ${!v}"
    else
      fail "目录 $v 不存在: ${!v}"; rc=1
    fi
  done
  if [ -f "${FACTS_DICT_PATH:-}" ]; then ok "文件 FACTS_DICT_PATH → $FACTS_DICT_PATH"; else fail "文件 FACTS_DICT_PATH 不存在: ${FACTS_DICT_PATH:-未定义}"; rc=1; fi
  if [ -x "$LMS_HOME/.venv/bin/python" ]; then ok "LMS venv python → $LMS_HOME/.venv/bin/python"; else fail "LMS venv python 缺失: $LMS_HOME/.venv/bin/python"; rc=1; fi
  if [ -f "$LMS_HOME/.env" ]; then ok "LMS .env（密钥）存在"; else fail "LMS .env 缺失: $LMS_HOME/.env（无法启动 lms-api）"; rc=1; fi
  if [ -f "$GLUE_HOME/glue_server.py" ]; then ok "glue_server.py 存在"; else fail "glue_server.py 缺失: $GLUE_HOME/glue_server.py"; rc=1; fi
  if [ -f "$SANDGLASS_SOURCE/sandglass_http_api.py" ]; then ok "sandglass_http_api.py 存在"; else fail "sandglass_http_api.py 缺失"; rc=1; fi
  if [ -f "$ISO_SAND_HOME/start_scheduler.sh" ] && [ -f "$ISO_SAND_HOME/start_consumer.sh" ]; then ok "iso-sand 启动脚本存在"; else fail "iso-sand 启动脚本缺失"; rc=1; fi
  if [ -f "$VERIFY_HOME/src/verify_daemon.py" ]; then ok "verify_daemon.py 存在"; else fail "verify_daemon.py 缺失"; rc=1; fi

  echo "── [4/5] 端口状态 ──"
  for port in "$SANDGLASS_API_PORT" "$LMS_API_PORT" "$GLUE_PORT" "$EDITOR_PORT"; do
    if ss -tln 2>/dev/null | grep -q ":$port "; then
      listener=$(ss -tlnp 2>/dev/null | grep ":$port " | head -1)
      ok "端口 $port 已监听（${listener##*users:}）"
    else
      warn "端口 $port 空闲（服务未运行——正常，start 后占用）"
    fi
  done

  echo "── [5/5] 依赖命令 ──"
  for c in python3 curl ss pgrep setsid bash; do
    if command -v "$c" > /dev/null 2>&1; then
      ok "命令 $c ✓"
    else
      fail "命令 $c 缺失"; rc=1
    fi
  done

  echo ""
  if [ "$rc" -eq 0 ]; then
    ok "doctor 全绿：配置就绪，可 ./stack_ctl.sh start"
  else
    fail "doctor 存在异常项（见上），修复后重试"
  fi
  return $rc
}

# ---------- 主命令 ----------
TARGET="${2:-}"

case "$CMD" in
  setup)
    echo "=== stack_ctl setup — 首次部署向导 ==="
    if [ -f "$AGENT_OS_HOME/env.local" ]; then
      ok "env.local 已存在（跳过生成）"
    elif [ -f "$AGENT_OS_HOME/env.template" ]; then
      cp "$AGENT_OS_HOME/env.template" "$AGENT_OS_HOME/env.local"
      warn "已从 env.template 生成 env.local —— 请编辑【A. 机器根变量】为本机实际路径"
    else
      fail "缺少 env.template，无法生成配置"; exit 1
    fi
    echo ""
    doctor_run "$AGENT_OS_HOME/env.local"
    ;;
  doctor)
    doctor_run "$AGENT_OS_HOME/env.local"
    ;;
  list)
    echo "服务清单（共 ${#SERVICES[@]} 个）："
    for s in "${SERVICES[@]}"; do
      IFS='|' read -r name cwd cmd envf port health deps desc <<< "$s"
      printf "  %-12s %s%s\n" "$name" "$desc" "$( [ -n "$port" ] && echo " [:${port}]" )"
    done
    ;;
  status)
    echo "=== 轻如烟体系服务状态 ($(date '+%F %T')) ==="
    all_ok=1
    for s in "${SERVICES[@]}"; do
      IFS='|' read -r name cwd cmd envf port health deps desc <<< "$s"
      if svc_healthy "$name" "$cwd" "$cmd" "$envf" "$port" "$health" "$deps" "$desc"; then
        pid=$(pid_by_port "$port" 2>/dev/null)
        if [ -z "$pid" ] && [ -f "$RUN_DIR/${name}.pid" ]; then pid=$(cat "$RUN_DIR/${name}.pid"); fi
        if [ -z "$pid" ] && [ -f "$ISO_SAND_HOME/data/${name}.pid" ]; then pid=$(cat "$ISO_SAND_HOME/data/${name}.pid"); fi
        if [ -z "$pid" ]; then pid=$(pgrep -f ".run_${name}" 2>/dev/null | head -1); fi
        if [ -z "$pid" ] && [ "$name" = "verify" ]; then pid=$(pgrep -f "verify_daemon" 2>/dev/null | head -1); fi
        ok "$name  [:${port:-无}] PID=${pid:-?}"
      else
        fail "$name  [:${port:-无}] 未运行（${desc}）"; all_ok=0
      fi
    done
    [ "$all_ok" -eq 1 ] && echo -e "\n${C_GREEN}全部服务健康 ✅${C_RST}" || echo -e "\n${C_RED}存在未运行服务 ❌（可用 ./stack_ctl.sh start 启动）${C_RST}"
    ;;
  health)
    # 深度健康：HTTP 层逐个探测
    echo "=== 深度健康检查 ==="
    for s in "${SERVICES[@]}"; do
      IFS='|' read -r name cwd cmd envf port health deps desc <<< "$s"
      if [ -n "$health" ] && [ -n "$port" ]; then
        code=$(curl -s -o /dev/null -w "%{http_code}" -m 3 "http://127.0.0.1:${port}${health}" 2>/dev/null)
        [ "$code" = "200" ] && ok "$name ${health} → 200" || fail "$name ${health} → ${code:-超时}"
      else
        svc_healthy "$name" "$cwd" "$cmd" "$envf" "$port" "$health" "$deps" "$desc" && ok "$name 进程存活" || fail "$name 进程不在"
      fi
    done
    ;;
  start)
    echo "=== 启动全部服务（依赖顺序）==="
    # 简单拓扑：按清单顺序（清单已按依赖排布），依赖前置检查
    for s in "${SERVICES[@]}"; do
      IFS='|' read -r name cwd cmd envf port health deps desc <<< "$s"
      svc_start "$name" "$cwd" "$cmd" "$envf" "$port" "$health" "$deps" "$desc" || true
    done
    ;;
  stop)
    echo "=== 停止全部服务（逆序）==="
    for ((i=${#SERVICES[@]}-1; i>=0; i--)); do
      IFS='|' read -r name cwd cmd envf port health deps desc <<< "${SERVICES[$i]}"
      svc_stop "$name" "$cwd" "$cmd" "$envf" "$port" "$health" "$deps" "$desc"
    done
    ;;
  restart)
    if [ -n "$TARGET" ]; then
      # 重启单个：找到该服务
      for s in "${SERVICES[@]}"; do
        IFS='|' read -r name cwd cmd envf port health deps desc <<< "$s"
        [ "$name" = "$TARGET" ] || continue
        echo "=== 重启 $name ==="
        svc_stop "$name" "$cwd" "$cmd" "$envf" "$port" "$health" "$deps" "$desc"
        svc_start "$name" "$cwd" "$cmd" "$envf" "$port" "$health" "$deps" "$desc"
        exit $?
      done
      fail "未知服务: $TARGET（可用 ./stack_ctl.sh list 查看）"; exit 1
    else
      "$0" stop && "$0" start
    fi
    ;;
  logs)
    [ -z "$TARGET" ] && { echo "用法: ./stack_ctl.sh logs <服务名>"; exit 1; }
    tail -f "$LOG_DIR/${TARGET}.log" 2>/dev/null || fail "日志不存在: $LOG_DIR/${TARGET}.log"
    ;;
  *)
    echo "用法: $0 {setup|doctor|start|stop|restart [服务]|status|health|list|logs <服务>}"
    exit 1
    ;;
esac
