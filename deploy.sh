#!/bin/bash
# =============================================================
# deploy.sh — 一键部署总控（2026-08-12 新增，复现保障配套）
# -------------------------------------------------------------
# 一个命令完整部署：前置检测 → 逐项提示缺什么 → 按依赖顺序拉起
#   （沙漏→LMS→胶水→总线 scheduler/consumer→玄鉴→编辑器→cron 检查）
#   → 每步健康验证 → 最终汇总。
#
# 用法:
#   bash deploy.sh               # 完整部署（幂等：已在跑的服务自动跳过）
#   bash deploy.sh doctor        # 只做前置检测，不启动
#   bash deploy.sh status        # 全栈状态汇总（复用 stack_ctl.sh + 编辑器/OpenClaw/cron）
#   bash deploy.sh stop          # 全栈停止（委托 stack_ctl.sh stop，不含编辑器/OpenClaw）
#   bash deploy.sh verify        # 部署后深度验证（关键数据点，对齐 SYSTEM.md §3.5）
#   bash deploy.sh cron          # crontab 检查（列出缺失条目，不自动写入）
#   bash deploy.sh cron-show     # 打印推荐 crontab 全表（供部署者复制）
#
# 设计原则：
#   - 零硬编码：路径全部来自 env.local（配置中心），缺失时相对推导兜底
#   - 6 服务启动/停止委托 stack_ctl.sh（表驱动、幂等、依赖顺序、优雅停机）
#   - 与 lms_ctl.sh 兼容（LMS 统一由 stack_ctl.sh 以非 systemd 模式管理）
#   - 本机验证过的服务：全部幂等，可重复执行
# =============================================================
set -u

AGENT_OS_HOME="$(cd "$(dirname "$0")" && pwd)"
# ── 配置加载：env.local 唯一权威，缺失则相对推导 ──
if [ -f "$AGENT_OS_HOME/env.local" ]; then
    set -a; . "$AGENT_OS_HOME/env.local"; set +a
fi
LIGHT_HOME="${LIGHT_HOME:-$AGENT_OS_HOME/../所有自动化/轻如烟}"
LMS_HOME="${LMS_HOME:-$AGENT_OS_HOME/../living-memory-system-cloud}"
GLUE_HOME="${GLUE_HOME:-$AGENT_OS_HOME/../memory-integration-layer}"
# 玄鉴已并入 agent-os/xuanjian（2026-08-12，复现缺口清单 #2）。
# 默认优先新路径；旧同构沙盘保留为回退（本机运行中守护进程仍在旧位置，data/ 不随仓分发）。
if [ -d "$AGENT_OS_HOME/xuanjian/src" ]; then
    VERIFY_HOME="${VERIFY_HOME:-$AGENT_OS_HOME/xuanjian}"
else
    VERIFY_HOME="${VERIFY_HOME:-$AGENT_OS_HOME/../AgentOS-IsoSand/同构沙盘}"
fi
SANDGLASS_SOURCE="${SANDGLASS_SOURCE:-$LIGHT_HOME/sandglass_source}"
NEXSANDBASE_HOME="${NEXSANDBASE_HOME:-$LIGHT_HOME/sandglass}"
ISO_SAND_HOME="${ISO_SAND_HOME:-$AGENT_OS_HOME/iso-sand}"
EDITOR_HOME="${EDITOR_HOME:-$LIGHT_HOME/scripts}"
RUN_DIR="${RUN_DIR:-$AGENT_OS_HOME/run}"
LOG_DIR="${LOG_DIR:-$AGENT_OS_HOME/logs}"
SANDGLASS_API_PORT="${SANDGLASS_API_PORT:-17333}"
LMS_API_PORT="${LMS_API_PORT:-8190}"
GLUE_PORT="${GLUE_PORT:-19000}"
EDITOR_PORT="${EDITOR_PORT:-18888}"
OPENCLAW_PORT="${OPENCLAW_PORT:-10554}"
LMS_CLOUD_EMBED_URL="${LMS_CLOUD_EMBED_URL:-http://127.0.0.1:11435/v1/embeddings}"
LMS_CLOUD_EMBED_MODEL="${LMS_CLOUD_EMBED_MODEL:-bge-m3}"
# OpenClaw 配置（机器相关，找不到则跳过该项检查）
OPENCLAW_JSON="${OPENCLAW_JSON:-$HOME/.openclaw/openclaw.json}"

CMD="${1:-deploy}"

# 非 TTY（管道/日志/子进程）时禁用颜色，避免输出污染
if [ -t 1 ]; then
    C_GREEN='\033[0;32m'; C_RED='\033[0;31m'; C_YEL='\033[1;33m'; C_DIM='\033[2m'; C_RST='\033[0m'
else
    C_GREEN=''; C_RED=''; C_YEL=''; C_DIM=''; C_RST=''
fi
ok()   { echo -e "${C_GREEN}✅ $1${C_RST}"; }
fail() { echo -e "${C_RED}❌ $1${C_RST}"; }
warn() { echo -e "${C_YEL}⚠️  $1${C_RST}"; }
dim()  { echo -e "${C_DIM}$1${C_RST}"; }

mkdir -p "$RUN_DIR" "$LOG_DIR"

# ══════════════════════════════════════════════════════════════
# 1. 前置检测（preflight）——逐项提示缺什么
# ══════════════════════════════════════════════════════════════
preflight() {
    local rc=0

    echo "═══ [1/7] 配置中心 env.local ═══"
    if [ -f "$AGENT_OS_HOME/env.local" ]; then
        ok "env.local 存在: $AGENT_OS_HOME/env.local"
    elif [ -f "$AGENT_OS_HOME/env.template" ]; then
        fail "env.local 缺失（执行: cd \"$AGENT_OS_HOME\" && ./stack_ctl.sh setup 生成）"
        rc=1
    else
        fail "env.local 与 env.template 均缺失 —— 仓库不完整，请重新 clone agent-os"
        rc=1
    fi

    echo "═══ [2/7] 仓库目录（5 个模块） ═══"
    for v in "LIGHT_HOME:$LIGHT_HOME" "LMS_HOME:$LMS_HOME" "GLUE_HOME:$GLUE_HOME" \
             "SANDGLASS_SOURCE:$SANDGLASS_SOURCE" "NEXSANDBASE_HOME:$NEXSANDBASE_HOME" \
             "ISO_SAND_HOME:$ISO_SAND_HOME" "VERIFY_HOME:$VERIFY_HOME"; do
        local name="${v%%:*}" path="${v#*:}"
        if [ -d "$path" ]; then ok "目录 $name → $path"; else fail "目录 $name 不存在: $path（检查 env.local A 节路径）"; rc=1; fi
    done
    [ -f "$SANDGLASS_SOURCE/sandglass_http_api.py" ] || { fail "沙漏源码缺 sandglass_http_api.py（clone tdx1146/nyx 到 SANDGLASS_SOURCE）"; rc=1; }
    [ -f "$GLUE_HOME/glue_server.py" ] || { fail "胶水层缺 glue_server.py（clone tdx1146/memory-integration-layer）"; rc=1; }
    [ -f "$VERIFY_HOME/src/verify_daemon.py" ] || { warn "玄鉴缺 src/verify_daemon.py（xuanjian/ 未检出或源码缺失；见复现缺口清单 #2；可暂缓，不影响核心链路）"; }

    echo "═══ [3/7] Python / node 运行时 ═══"
    if command -v python3 > /dev/null 2>&1; then
        local pyv; pyv=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
        if [ "$(echo "$pyv" | cut -d. -f1)" -ge 3 ] && [ "$(echo "$pyv" | cut -d. -f2)" -ge 10 ]; then
            ok "python3 $(python3 --version 2>&1 | grep -oP '\d+\.\d+\.\d+')（LMS 要求 ≥3.10，本机实测 3.11）"
            [ "$(echo "$pyv" | cut -d. -f2)" -lt 11 ] && warn "python3 为 3.$pyv，沙漏/胶水实测为 3.11，建议升级"
        else
            fail "python3 $pyv < 3.10（LMS 最低要求）"; rc=1
        fi
    else
        fail "python3 未安装"; rc=1
    fi
    if command -v node > /dev/null 2>&1; then
        local nv; nv=$(node --version 2>&1 | tr -d 'v' | cut -d. -f1)
        [ "$nv" -ge 18 ] 2>/dev/null && ok "node $(node --version 2>&1)（≥18）" || { fail "node $(node --version 2>&1) < 18（OpenClaw 运行时要求）"; rc=1; }
    else
        fail "node 未安装（OpenClaw Gateway 运行时必需）"; rc=1
    fi

    echo "═══ [4/7] LMS venv 与 .env（密钥） ═══"
    if [ -x "$LMS_HOME/.venv/bin/python" ]; then
        ok "venv 存在: $LMS_HOME/.venv/bin/python"
    else
        fail "LMS venv 缺失（执行: cd \"$LMS_HOME\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt）"; rc=1
    fi
    if [ -f "$LMS_HOME/.env" ]; then
        ok "LMS .env 存在"
        grep -q '^LMS_EMBEDDER=cloud' "$LMS_HOME/.env" 2>/dev/null && ok "LMS_EMBEDDER=cloud（HF 不可达，必须 cloud）" || warn "LMS .env 未设 LMS_EMBEDDER=cloud（否则嵌入静默降级，见 SYSTEM.md 坑 3）"
    else
        fail "LMS .env 缺失（执行: cd \"$LMS_HOME\" && cp .env.example .env 后填入 DEEPSEEK_API_KEY / LMS_CLOUD_EMBED_URL 等）"; rc=1
    fi

    echo "═══ [5/7] 外部依赖：embed 向量服务（bge-m3） ═══"
    local code; code=$(curl -s --max-time 6 -o /tmp/deploy_embed_probe.json -w '%{http_code}' \
        -X POST "$LMS_CLOUD_EMBED_URL" -H 'Content-Type: application/json' \
        -d "{\"model\":\"$LMS_CLOUD_EMBED_MODEL\",\"input\":\"ping\"}" 2>/dev/null)
    if [ "$code" = "200" ]; then
        ok "embed 服务可达: $LMS_CLOUD_EMBED_URL（model=$LMS_CLOUD_EMBED_MODEL）"
    else
        fail "embed 服务不可达: $LMS_CLOUD_EMBED_URL（HTTP $code）—— 这是 LMS/胶水感官层，缺它=静默降级"
        warn "  修复：在任意机器起 Ollama + bge-m3（1024 维），暴露 /v1/embeddings；或配 LMS_CLOUD_EMBED_FALLBACK_URL 隧道备用"
        rc=1
    fi

    echo "═══ [6/7] OpenClaw Gateway（宿主，可选但强烈建议） ═══"
    if ss -tln 2>/dev/null | grep -q ":$OPENCLAW_PORT "; then
        ok "OpenClaw Gateway 监听 :$OPENCLAW_PORT"
        if [ -f "$OPENCLAW_JSON" ]; then
            grep -q "glue-memory-injector" "$OPENCLAW_JSON" 2>/dev/null && ok "插件 glue-memory-injector 已注册" || warn "openclaw.json 未发现 glue-memory-injector 插件（记忆注入不会生效）"
            for mcp in lms-memory lms-http shouji-memory; do
                grep -q "\"$mcp\"" "$OPENCLAW_JSON" 2>/dev/null && ok "MCP $mcp 已注册" || warn "MCP $mcp 未注册"
            done
        else
            warn "未找到 openclaw.json（$OPENCLAW_JSON），跳过插件/MCP 检查"
        fi
    else
        warn "OpenClaw Gateway 未监听 :$OPENCLAW_PORT —— 主 AI 宿主需单独安装启动（不在本脚本拉起范围）"
    fi

    echo "═══ [7/7] 编辑器（落沙写入口，:${EDITOR_PORT}） ═══"
    if curl -sf --max-time 3 "http://127.0.0.1:$EDITOR_PORT/" > /dev/null 2>&1; then
        ok "编辑器 :$EDITOR_PORT 运行中"
    else
        if [ -f "$EDITOR_HOME/edit-web.py" ]; then
            warn "编辑器未运行（deploy 时会自动拉起）"
        else
            fail "编辑器源码缺失: $EDITOR_HOME/edit-web.py（clone tdx1146/edit-web.py 到 EDITOR_HOME）"; rc=1
        fi
    fi

    echo ""
    if [ "$rc" -eq 0 ]; then
        ok "前置检测全绿 —— 可执行 bash deploy.sh 完整部署"
    else
        fail "前置检测存在 ${rc} 类缺失项（见上逐项修复；玄鉴缺失可暂缓）"
    fi
    return $rc
}

# ══════════════════════════════════════════════════════════════
# 2. 拉起编辑器（幂等；health-check.sh 同款启动方式）
# ══════════════════════════════════════════════════════════════
start_editor() {
    if curl -sf --max-time 3 "http://127.0.0.1:$EDITOR_PORT/" > /dev/null 2>&1; then
        ok "编辑器已在运行 :$EDITOR_PORT，跳过"
        return 0
    fi
    if [ ! -f "$EDITOR_HOME/edit-web.py" ]; then
        fail "编辑器源码缺失: $EDITOR_HOME/edit-web.py（clone tdx1146/edit-web.py）"
        return 1
    fi
    echo "  → 启动编辑器 :$EDITOR_PORT ..."
    ( cd "$LIGHT_HOME" && nohup python3 "$EDITOR_HOME/edit-web.py" > /tmp/edit-web-restart.log 2>&1 & )
    sleep 3
    if curl -sf --max-time 3 "http://127.0.0.1:$EDITOR_PORT/" > /dev/null 2>&1; then
        ok "编辑器就绪 :$EDITOR_PORT"
        return 0
    else
        fail "编辑器启动失败，日志: /tmp/edit-web-restart.log（tail）"
        tail -5 /tmp/edit-web-restart.log 2>/dev/null | sed 's/^/    /'
        return 1
    fi
}

# LMS 状态摘要：/status 会话按需加载（冷启动后首次访问会 404），用快照兜底判断
lms_status_summary() {
    local out; out=$(curl -s --max-time 5 "http://127.0.0.1:$LMS_API_PORT/status/main" 2>/dev/null)
    local tc; tc=$(printf '%s' "$out" | python3 -c "import json,sys
 try:
  d=json.load(sys.stdin).get('status',{}); print(d.get('turn_count',''))
 except Exception: print('')" 2>/dev/null)
    if [ -n "$tc" ]; then
        echo "turn_count=$tc"
    else
        local snap; snap=$(ls "$LMS_HOME/snapshots/main/" 2>/dev/null | wc -l)
        if [ "$snap" -gt 0 ] 2>/dev/null; then
            echo "会话未加载（快照 $snap 条在，下轮对话自动恢复；非降级）"
        else
            echo "turn_count=空（无快照；若 /health 200 但无会话=静默降级，查 .env 是否 source）"
        fi
    fi
}

# ══════════════════════════════════════════════════════════════
# 3. 部署后逐服务健康验证（对齐 SYSTEM.md §3.2 验证命令）
# ══════════════════════════════════════════════════════════════
verify_services() {
    local allok=1

    echo "── 核心链路逐服务健康验证 ──"
    if curl -sf --max-time 5 "http://127.0.0.1:$SANDGLASS_API_PORT/api/health" > /dev/null 2>&1; then
        local cnt; cnt=$(curl -s --max-time 5 "http://127.0.0.1:$SANDGLASS_API_PORT/api/health" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('sandglass_count','?'))" 2>/dev/null)
        ok "沙漏 :$SANDGLASS_API_PORT /api/health（sandglass_count=$cnt）"
    else
        fail "沙漏 :$SANDGLASS_API_PORT 不可达（日志: $LOG_DIR/sandglass_http_api.log）"; allok=0
    fi

    if curl -sf --max-time 5 "http://127.0.0.1:$LMS_API_PORT/health" > /dev/null 2>&1; then
        ok "LMS :$LMS_API_PORT /health（$(lms_status_summary)）"
    else
        fail "LMS :$LMS_API_PORT 不可达（日志: $LOG_DIR/lms_api.log）"; allok=0
    fi

    if curl -sf --max-time 5 "http://127.0.0.1:$GLUE_PORT/health" > /dev/null 2>&1; then
        local bk; bk=$(curl -s --max-time 5 "http://127.0.0.1:$GLUE_PORT/health" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d.get('backends',{}),ensure_ascii=False))" 2>/dev/null)
        ok "胶水 :$GLUE_PORT /health（backends=$bk）"
    else
        fail "胶水 :$GLUE_PORT 不可达（日志: $LOG_DIR/glue_server.log）"; allok=0
    fi

    local s_pid c_pid
    s_pid=$(cat "$ISO_SAND_HOME/data/scheduler.pid" 2>/dev/null); c_pid=$(cat "$ISO_SAND_HOME/data/consumer.pid" 2>/dev/null)
    if kill -0 "$s_pid" 2>/dev/null && kill -0 "$c_pid" 2>/dev/null; then
        ok "总线 scheduler(PID=$s_pid) + consumer(PID=$c_pid) 存活"
    else
        fail "总线 scheduler/consumer 未全部存活（scheduler=$s_pid consumer=$c_pid，日志: $LOG_DIR/scheduler.log $LOG_DIR/consumer.log）"; allok=0
    fi

    if [ -f "$VERIFY_HOME/data/daemon.pid" ] && kill -0 "$(cat "$VERIFY_HOME/data/daemon.pid")" 2>/dev/null; then
        ok "玄鉴 verify_daemon 存活（PID=$(cat "$VERIFY_HOME/data/daemon.pid")）"
    else
        warn "玄鉴未存活（源码缺失或未启动；不影响明暗双线核心，见复现缺口清单）"
    fi

    echo "── 写入口与数据流验证 ──"
    if curl -sf --max-time 3 "http://127.0.0.1:$EDITOR_PORT/" > /dev/null 2>&1; then
        ok "编辑器 :$EDITOR_PORT 运行中（发一条消息 → 沙漏 txt 应出现新行）"
    else
        warn "编辑器 :$EDITOR_PORT 未运行（明线落沙入口缺失！）"; allok=0
    fi
    local txt_tail; txt_tail=$(tail -1 "$NEXSANDBASE_HOME/sandglass.txt" 2>/dev/null | head -c 80)
    [ -n "$txt_tail" ] && ok "沙漏 txt 尾部: $txt_tail" || warn "sandglass.txt 为空或不可读（$NEXSANDBASE_HOME/sandglass.txt）"

    # allok=1 成功 / 0 失败 → 映射为退出码 0/1
    [ "$allok" -eq 1 ] && return 0 || return 1
}

# ══════════════════════════════════════════════════════════════
# 4. crontab 检查（只读，不自动写入）
# ══════════════════════════════════════════════════════════════
cron_check() {
    local crontab_now; crontab_now=$(crontab -l 2>/dev/null || true)
    local missing=0

    echo "═══ crontab 检查（对齐 SYSTEM.md §3.4 全表） ═══"
    # 格式：关键词|说明
    local entries=(
      "pulse-cron|self_pulse 唤醒链（*/10，怀疑/唤醒三锁之一）"
      "night_patrol_run|夜巡（30 23，怀疑/唤醒三锁之一）"
      "session-reset-watchdog|会话重置看门狗（*/2，怀疑/唤醒三锁之一）"
      "health-check.sh|编辑器自愈（*/5）"
      "lms_backup.sh --quick|LMS 快照备份（*/15）"
      "lms_backup.sh --hourly|LMS 归档备份（0 *）"
      "lms_backup.sh --daily|LMS 全量备份（30 2）"
      "start_all.sh|开机自启（@reboot sleep 20）"
      "system_health_check.sh|系统健康巡检（*/30）"
      "contract_check.sh|契约层巡检（*/30）"
      "sandglass_sync.sh|沙漏 db 镜像同步（*/10）"
      "gen_dashboard.sh|健康看板生成（*/5）"
    )
    local item kw desc
    for item in "${entries[@]}"; do
        kw="${item%%|*}"; desc="${item#*|}"
        if printf '%s' "$crontab_now" | grep -qF "$kw"; then
            ok "$desc（$kw）"
        else
            warn "缺失: $desc —— 条目含: $kw"
            missing=1
        fi
    done
    [ "$missing" -eq 0 ] && ok "crontab 全表完整" || warn "缺失条目请手动 crontab -e 添加（或 bash deploy.sh cron-show 查看推荐全表）"
}

cron_show() {
    cat <<'EOF'
# ===== 推荐 crontab 全表（部署参考，路径按本机 env.local 替换） =====
# LMS 备份三档
*/15 * * * *  $LMS_HOME/scripts/lms_backup.sh --quick
0 * * * *     $LMS_HOME/scripts/lms_backup.sh --hourly
30 2 * * *    $LMS_HOME/scripts/lms_backup.sh --daily
# 开机自启（LMS 由 lms_ctl.sh 幂等拉起；全栈由 start_all.sh）
@reboot       sleep 30 && bash $LMS_HOME/scripts/lms_ctl.sh start
@reboot       sleep 45 && setsid $LMS_HOME/.venv/bin/python $LMS_HOME/scripts/run_control.py --host 127.0.0.1 --port 8191 < /dev/null &
@reboot       sleep 20 && bash "$AGENT_OS_HOME/start_all.sh"
# 怀疑/唤醒三锁
*/10 * * * *  bash $LIGHT_HOME/scripts/pulse-cron.sh
30 23 * * *   bash "$AGENT_OS_HOME/doubt-system/night_patrol_run.sh"
*/2 * * * *   python3 $LIGHT_HOME/scripts/session-reset-watchdog.py
# 自愈/巡检
*/5 * * * *   bash $LIGHT_HOME/scripts/health-check.sh
*/30 * * * *  bash "$AGENT_OS_HOME/scripts/system_health_check.sh" --cron
*/30 * * * *  bash "$AGENT_OS_HOME/scripts/contract_check.sh" --cron
*/10 * * * *  bash "$AGENT_OS_HOME/scripts/sandglass_sync.sh"
*/5 * * * *   bash "$AGENT_OS_HOME/scripts/gen_dashboard.sh"
EOF
}

# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════
case "$CMD" in
  doctor|preflight)
    preflight; exit $?
    ;;
  cron)
    cron_check; exit 0
    ;;
  cron-show)
    cron_show; exit 0
    ;;
  status)
    echo "=== deploy.sh status（$(date '+%F %T')） ==="
    bash "$AGENT_OS_HOME/stack_ctl.sh" status
    echo ""
    echo "── 宿主与写入口 ──"
    curl -sf --max-time 3 "http://127.0.0.1:$EDITOR_PORT/" > /dev/null 2>&1 && ok "编辑器 :$EDITOR_PORT 运行中" || warn "编辑器 :$EDITOR_PORT 未运行"
    ss -tln 2>/dev/null | grep -q ":$OPENCLAW_PORT " && ok "OpenClaw Gateway :$OPENCLAW_PORT 监听中" || warn "OpenClaw Gateway :$OPENCLAW_PORT 未监听"
    echo ""
    cron_check
    echo ""
    echo "── 关键数据点 ──"
    curl -s --max-time 5 "http://127.0.0.1:$SANDGLASS_API_PORT/api/health" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print('  沙漏 sandglass_count:', d.get('sandglass_count'))" 2>/dev/null || echo "  沙漏 API 不可达"
    curl -s --max-time 5 "http://127.0.0.1:$LMS_API_PORT/health" > /dev/null 2>&1 && echo "  LMS: $(lms_status_summary)" || echo "  LMS 不可达"
    echo "  总线尾部: $(tail -1 "$ISO_SAND_HOME/data/event_bus.jsonl" 2>/dev/null | head -c 100 || echo 无)"
    exit 0
    ;;
  stop)
    echo "=== deploy.sh stop（$(date '+%F %T')） ==="
    echo "注：停 6 服务栈（复用 stop_all.sh：含玄鉴/总线双 PID 文件）；编辑器/OpenClaw 属宿主层，不在停止范围。"
    bash "$AGENT_OS_HOME/stop_all.sh"
    exit $?
    ;;
  verify)
    verify_services
    exit $?
    ;;
  deploy|"")
    echo "════════════════════════════════════════════════"
    echo "  Agent OS 一键部署（deploy.sh）$(date '+%F %T')"
    echo "════════════════════════════════════════════════"
    echo ""
    # 1. 前置检测：失败则中止（给出修复指引）
    if ! preflight; then
        echo ""
        fail "前置检测未通过，请按上述提示修复后重试（或 bash deploy.sh doctor 复查）"
        exit 1
    fi
    echo ""
    # 2. 按依赖顺序拉起 6 服务（stack_ctl.sh 内部已按 沙漏→LMS→胶水→总线→玄鉴 顺序 + 幂等）
    echo "── 拉起 6 服务栈（依赖顺序，幂等） ──"
    bash "$AGENT_OS_HOME/stack_ctl.sh" start
    echo ""
    # 3. 拉起编辑器（落沙写入口）
    start_editor
    echo ""
    # 4. 每步健康验证
    verify_services
    VRC_=$?
    echo ""
    # 5. crontab 检查（只读提示）
    cron_check
    echo ""
    echo "────────────────────────────────────────────────"
    if [ "$VRC_" -eq 0 ]; then
        ok "一键部署完成 —— 核心链路全绿；日常查健康: bash deploy.sh status / bash scripts/system_health_check.sh"
    else
        fail "部署完成但存在红项（见上）；修复后重跑 bash deploy.sh（幂等）"
    fi
    exit $VRC_
    ;;
  *)
    echo "用法: bash deploy.sh [deploy|doctor|status|stop|verify|cron|cron-show]"
    echo "  deploy      完整部署（默认）"
    echo "  doctor      只做前置检测"
    echo "  status      全栈状态汇总"
    echo "  stop        停止 6 服务栈"
    echo "  verify      部署后深度验证"
    echo "  cron        检查 crontab 缺失条目"
    echo "  cron-show   打印推荐 crontab 全表"
    exit 1
    ;;
esac
