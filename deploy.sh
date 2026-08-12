#!/bin/bash
# =============================================================
# deploy.sh — 一键部署总控（2026-08-12 新增，2026-08-13 升级为安装器）
# -------------------------------------------------------------
# 一个命令从零到全绿：bootstrap（自动 clone 6 仓/venv/.env/数据目录）
#   → 前置检测（缺→自动修→修不了给可复制命令，不中止）→ 按依赖顺序拉起
#   （沙漏→LMS→胶水→总线 scheduler/consumer→玄鉴→编辑器→cron 检查）
#   → 每步健康验证 → 最终汇总。
#
# 用法:
#   bash deploy.sh               # 完整部署（bootstrap + 自动修复 + 拉起；幂等）
#   bash deploy.sh bootstrap     # 只做环境安装（clone/venv/.env/数据目录），不启动
#   bash deploy.sh doctor        # 只做前置检测（不自动修复、不启动）
#   bash deploy.sh status        # 全栈状态汇总（复用 stack_ctl.sh + 编辑器/OpenClaw/cron）
#   bash deploy.sh stop          # 全栈停止（委托 stack_ctl.sh stop，不含编辑器/OpenClaw）
#   bash deploy.sh verify        # 部署后深度验证（关键数据点，对齐 SYSTEM.md §3.5）
#   bash deploy.sh cron          # crontab 检查（列出缺失条目，不自动写入）
#   bash deploy.sh cron-show     # 打印推荐 crontab 全表（已按 env.local 展开，可直接复制）
#   bash deploy.sh cron-install  # 合并安装推荐 crontab（备份→去重→幂等）
#
# 设计原则：
#   - 零硬编码：路径全部来自 env.local（配置中心），缺失时相对推导兜底
#   - 自动修复只补"缺失/占位符"，绝不覆盖已配置的真实值
#   - 系统级安装（python/node/embed/OpenClaw/cron 写 crontab）不自动做，
#     只给可复制命令 + 校验；仓库级安装（clone/venv/.env/数据目录）自动做
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
# AGENT_OS_HOME 以脚本位置为准（env.local 里的值仅作参考，防止占位符/搬迁后错位）
AGENT_OS_HOME="$(cd "$(dirname "$0")" && pwd)"
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
LMS_CLOUD_EMBED_DIM="${LMS_CLOUD_EMBED_DIM:-1024}"
# OpenClaw 配置（机器相关，找不到则跳过该项检查）
OPENCLAW_JSON="${OPENCLAW_JSON:-$HOME/.openclaw/openclaw.json}"
# 插件目录（bootstrap 把 glue-memory-injector clone 到这里）
PLUGIN_HOME="${PLUGIN_HOME:-$HOME/.openclaw/plugins}"

# 仓库注册表（bootstrap 自动 clone；全部公开，无需 token）。
# 注意：必须在 env.local 就绪（或 bootstrap 生成后）再初始化 —— 用 repos_init() 惰性重建。
GITHUB_BASE="${GITHUB_BASE:-https://github.com/tdx1146}"
repos_init() {
    REPOS=(
      "living-memory-system|$GITHUB_BASE/living-memory-system.git|$LMS_HOME"
      "memory-integration-layer|$GITHUB_BASE/memory-integration-layer.git|$GLUE_HOME"
      "nyx|$GITHUB_BASE/nyx.git|$SANDGLASS_SOURCE"
      "edit-web.py|$GITHUB_BASE/edit-web.py.git|$EDITOR_HOME"
      "glue-memory-injector|$GITHUB_BASE/glue-memory-injector.git|$PLUGIN_HOME/glue-memory-injector"
    )
}
repos_init

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
# 0. bootstrap —— 环境安装（幂等：已就绪跳过）
#    clone 6 仓 → LMS venv+pip → env.local/.env → 数据目录
#    embed/OpenClaw/cron：只给可复制命令 + 校验（不自动装系统级）
# ══════════════════════════════════════════════════════════════

# 克隆单个仓（幂等：目标已是 git 仓则跳过）
repo_clone() {  # name url dir
    local name="$1" url="$2" dir="$3"
    if [ -d "$dir/.git" ]; then
        ok "仓库 $name 已就绪: $dir（跳过 clone）"
        return 0
    fi
    if [ -e "$dir" ] && [ ! -d "$dir/.git" ]; then
        warn "仓库 $name 目标路径已存在但不是 git 仓: $dir —— 跳过 clone（请人工确认内容）"
        return 1
    fi
    echo "  → clone $name → $dir ..."
    mkdir -p "$(dirname "$dir")"
    if git clone --depth 1 "$url" "$dir" > /tmp/deploy-clone-$name.log 2>&1; then
        ok "clone $name 完成"
        return 0
    else
        fail "clone $name 失败（网络不通或仓不存在？日志: /tmp/deploy-clone-$name.log）"
        dim "    可复制命令: git clone $url $dir"
        return 1
    fi
}

# 生成 env.local：从模板复制 + A 节占位符替换为相对推导默认值（标准布局零手工）
# 只替换仍是占位符（含 <）的行，绝不覆盖已配置的真实值
env_local_generate() {
    [ -f "$AGENT_OS_HOME/env.template" ] || { fail "env.template 缺失，仓库不完整"; return 1; }
    cp "$AGENT_OS_HOME/env.template" "$AGENT_OS_HOME/env.local"
    # A 节占位符 → 相对推导默认值（标准布局：agent-os 与各仓同级）
    sed -i \
      -e "s|^AGENT_OS_HOME=.*|AGENT_OS_HOME=\"$AGENT_OS_HOME\"|" \
      -e "s|^LIGHT_HOME=.*|LIGHT_HOME=\"$LIGHT_HOME\"|" \
      -e "s|^LMS_HOME=.*|LMS_HOME=\"$LMS_HOME\"|" \
      -e "s|^GLUE_HOME=.*|GLUE_HOME=\"$GLUE_HOME\"|" \
      -e "s|^VERIFY_HOME=.*|VERIFY_HOME=\"\${AGENT_OS_HOME}/xuanjian\"|" \
      "$AGENT_OS_HOME/env.local"
    warn "已自动生成 env.local（A 节按标准布局填了默认路径）——如目录不在标准布局，请编辑 A 节；密钥类（FACTS_DICT_PATH/会话目录/embed URL）按实际机器填"
    # 重新加载
    set -a; . "$AGENT_OS_HOME/env.local"; set +a
    AGENT_OS_HOME="$(cd "$(dirname "$0")" && pwd)"
    return 0
}

# ── R-4（2026-08-13）：落沙 wrapper 必须位于编辑器的克隆根 ──
# edit-web.py 的 _sandglass_log 用 os.path.dirname(__file__)/sandglass_log_wrapper.py 定位；
# GitHub main（旧布局）把 wrapper 放在嵌套 scripts/ 下 → 新机器上 `if os.path.exists` 静默跳过
# = 每轮落沙零写入且无报错（部署成功但失忆，复验 R-4）。本函数把它铺平到克隆根，
# 缺失则 fail-loud（计入失败汇总，绝不静默）。幂等。
ensure_sandglass_wrapper() {
    local wrapper="$EDITOR_HOME/sandglass_log_wrapper.py"
    if [ -f "$wrapper" ]; then
        ok "落沙 wrapper 就位: $wrapper"
        return 0
    fi
    if [ -f "$EDITOR_HOME/scripts/sandglass_log_wrapper.py" ]; then
        cp "$EDITOR_HOME/scripts/sandglass_log_wrapper.py" "$wrapper" && chmod +x "$wrapper"
        ok "落沙 wrapper 已从嵌套 scripts/ 铺平到克隆根（R-4）: $wrapper"
        return 0
    fi
    fail "落沙 wrapper 缺失: $wrapper —— 编辑器每轮落沙将静默失败（失忆！）"
    dim "    修复: ① bash deploy.sh bootstrap（重新铺平）; ② 从 edit-web.py 仓 scripts/ 复制到克隆根; ③ 或等缺口 #3 合并（生产布局 wrapper 在顶层）"
    return 1
}

# ── R-1（2026-08-13）：self_pulse / health-check 接线到编辑器目录 ──
# 复验实锤：bootstrap 不复制 agent-os/self_pulse → $EDITOR_HOME，而 cron_show/cron_check 指向
# $LIGHT_HOME/scripts/pulse-cron.sh / session-reset-watchdog.py / health-check.sh（= EDITOR_HOME）
# → 3 条 cron 装了也是指向空文件的静默死条目。本函数幂等接线；缺失 fail-loud。
wire_editor_aux() {
    local failed=0
    if [ ! -d "$EDITOR_HOME" ]; then
        fail "EDITOR_HOME 不存在: $EDITOR_HOME（先 clone edit-web.py）"
        return 1
    fi
    # 1) self_pulse 套件（pulse-cron.sh + *.py）→ $EDITOR_HOME（不覆盖已存在的生产版）
    if [ -d "$AGENT_OS_HOME/self_pulse" ]; then
        local f dst
        for f in "$AGENT_OS_HOME/self_pulse/"*; do
            [ -f "$f" ] || continue
            case "$f" in
                *.py|*/pulse-cron.sh)
                    dst="$EDITOR_HOME/$(basename "$f")"
                    if [ ! -f "$dst" ]; then
                        cp "$f" "$dst" && chmod +x "$dst" && echo "  → 接线 $(basename "$f") → $EDITOR_HOME"
                    fi
                    ;;
            esac
        done
        if [ -f "$EDITOR_HOME/pulse-cron.sh" ] && [ -f "$EDITOR_HOME/session-reset-watchdog.py" ]; then
            ok "self_pulse 唤醒链已接线: pulse-cron.sh / session-reset-watchdog.py 等 → $EDITOR_HOME"
        else
            fail "self_pulse 接线失败: $EDITOR_HOME 仍缺 pulse-cron.sh 或 session-reset-watchdog.py"; failed=1
        fi
    else
        fail "agent-os/self_pulse 目录缺失（仓库不完整）—— 唤醒链 cron 将失效"; failed=1
    fi
    # 2) health-check.sh（编辑器自愈 */5）→ $EDITOR_HOME
    if [ -f "$AGENT_OS_HOME/scripts/health-check.sh" ]; then
        if [ ! -f "$EDITOR_HOME/health-check.sh" ]; then
            cp "$AGENT_OS_HOME/scripts/health-check.sh" "$EDITOR_HOME/health-check.sh" && chmod +x "$EDITOR_HOME/health-check.sh" && echo "  → 接线 health-check.sh → $EDITOR_HOME"
        fi
        if [ -f "$EDITOR_HOME/health-check.sh" ]; then
            ok "编辑器自愈 health-check.sh 已接线 → $EDITOR_HOME"
        else
            fail "health-check.sh 接线失败: $EDITOR_HOME/health-check.sh"; failed=1
        fi
    else
        fail "agent-os/scripts/health-check.sh 缺失（仓库不完整）—— 编辑器自愈 cron 将失效"; failed=1
    fi
    return $failed
}

# ── R-1（2026-08-13）：cron 目标脚本存在性校验（fail-loud——cron 指向不存在的脚本=静默失效）──
# 返回 0=全部就位；1=存在缺失（输出 ❌ + 修复指引）
verify_cron_targets() {
    local rc=0
    local pulse="$LIGHT_HOME/scripts/pulse-cron.sh"
    local watchdog="$LIGHT_HOME/scripts/session-reset-watchdog.py"
    local hcheck="$LIGHT_HOME/scripts/health-check.sh"
    local spec desc path
    for spec in "唤醒链 pulse-cron.sh|$pulse" "会话看门狗 session-reset-watchdog.py|$watchdog" "编辑器自愈 health-check.sh|$hcheck"; do
        desc="${spec%%|*}"; path="${spec#*|}"
        if [ -f "$path" ]; then
            ok "cron 目标 $desc → $path"
        else
            fail "cron 目标 $desc 缺失: $path —— 该 cron 将静默失效！运行 bash deploy.sh bootstrap 自动接线（R-1）"
            rc=1
        fi
    done
    return $rc
}

# 只把仍为占位符的 embed URL 修成本机 Ollama（绝不覆盖真实配置）
auto_fix_embed_placeholder() {
    local f="$AGENT_OS_HOME/env.local"
    [ -f "$f" ] || return 0
    if grep -qE '^LMS_CLOUD_EMBED_URL=.*<' "$f" 2>/dev/null && \
       curl -sf --max-time 3 -X POST "http://127.0.0.1:11434/v1/embeddings" -H 'Content-Type: application/json' -d "{\"model\":\"$LMS_CLOUD_EMBED_MODEL\",\"input\":\"ping\"}" -o /dev/null 2>/dev/null; then
        sed -i "s|^LMS_CLOUD_EMBED_URL=.*|LMS_CLOUD_EMBED_URL=\"http://127.0.0.1:11434/v1/embeddings\"|" "$f"
        sed -i "s|^VECTOR_URL=.*|VECTOR_URL=\"http://127.0.0.1:11434/v1/embeddings\"|" "$f"
        warn "检测到本机 Ollama(:11434) 可达，已把 env.local 的 embed 占位符修为 http://127.0.0.1:11434/v1/embeddings"
        set -a; . "$f"; set +a
    fi
}

bootstrap() {
    repos_init
    echo "═══ bootstrap：环境安装（幂等，已就绪跳过） ═══"

    # a. 自动 clone 6 仓（agent-os 自身已在）
    echo "── [a] 仓库（6 个：agent-os 已知 + 5 个自动 clone） ──"
    local failed=0
    for item in "${REPOS[@]}"; do
        IFS='|' read -r name url dir <<< "$item"
        repo_clone "$name" "$url" "$dir" || failed=1
    done
    ok "agent-os 自身: $AGENT_OS_HOME（clone 来源 tdx1146/agent-os）"
    # R-4（2026-08-13）：落沙 wrapper 铺平到编辑器克隆根（缺失 fail-loud，明线不断）
    ensure_sandglass_wrapper || failed=1
    # R-1（2026-08-13）：self_pulse / health-check 接线到编辑器目录（唤醒链/看门狗/自愈 cron 指向真实文件）
    wire_editor_aux || failed=1

    # b. LMS venv + pip install（唯一强制 venv 的仓；胶水零依赖、沙漏纯 stdlib）
    echo "── [b] LMS venv + 依赖 ──"
    if [ -x "$LMS_HOME/.venv/bin/python" ]; then
        ok "LMS venv 已就绪: $LMS_HOME/.venv/bin/python"
    elif [ -d "$LMS_HOME" ]; then
        echo "  → 创建 LMS venv（python3 -m venv .venv）..."
        if ( cd "$LMS_HOME" && python3 -m venv .venv ); then
            echo "  → pip install -r requirements.txt（torch 较大，可能耗时数分钟）..."
            if ( cd "$LMS_HOME" && .venv/bin/pip install -r requirements.txt > "$LOG_DIR/bootstrap-pip-lms.log" 2>&1 ); then
                ok "LMS 依赖安装完成"
            else
                fail "LMS pip install 失败（日志: $LOG_DIR/bootstrap-pip-lms.log 尾部）"
                tail -5 "$LOG_DIR/bootstrap-pip-lms.log" 2>/dev/null | sed 's/^/    /'
                dim "    可复制命令: cd \"$LMS_HOME\" && .venv/bin/pip install -r requirements.txt"
            fi
        else
            fail "LMS venv 创建失败（python3 -m venv 不可用？）"
            dim "    可复制命令: cd \"$LMS_HOME\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
        fi
    else
        fail "LMS 目录不存在（clone 失败或路径未配）: $LMS_HOME"
    fi

    # c. env.local / .env
    echo "── [c] 配置模板 → env.local / .env ──"
    if [ -f "$AGENT_OS_HOME/env.local" ]; then
        ok "env.local 已存在: $AGENT_OS_HOME/env.local"
        auto_fix_embed_placeholder
    else
        env_local_generate && ok "env.local 已从模板生成"
    fi
    if [ -f "$LMS_HOME/.env" ]; then
        ok "LMS .env 已存在"
    elif [ -f "$LMS_HOME/.env.example" ]; then
        cp "$LMS_HOME/.env.example" "$LMS_HOME/.env"
        warn "已 cp .env.example → $LMS_HOME/.env —— 请填入 DEEPSEEK_API_KEY / LMS_CLOUD_EMBED_URL（密钥不进仓库）"
    else
        warn "LMS 无 .env.example（仓库缺模板）—— 需手工创建 $LMS_HOME/.env（见 LMS README）"
    fi

    # d. 数据目录（沙漏数据/LMS 快照/总线/玄鉴 data/运行目录）
    echo "── [d] 数据目录 ──"
    local dirs=(
      "$NEXSANDBASE_HOME" "$NEXSANDBASE_HOME/persona"
      "$LMS_HOME/snapshots/main" "$ISO_SAND_HOME/data"
      "$VERIFY_HOME/data" "$LIGHT_HOME/memory" "$PLUGIN_HOME"
    )
    for d in "${dirs[@]}"; do
        if [ -n "$d" ] && [ ! -d "$d" ]; then mkdir -p "$d" && ok "mkdir $d"; fi
    done
    [ -d "$NEXSANDBASE_HOME" ] && ok "沙漏数据目录: $NEXSANDBASE_HOME（sandglass.txt 首次运行自动创建）"
    [ -d "$ISO_SAND_HOME/data" ] && ok "总线数据目录: $ISO_SAND_HOME/data"
    [ -d "$VERIFY_HOME/data" ] && ok "玄鉴数据目录: $VERIFY_HOME/data"

    # e. embed / OpenClaw / cron：可复制命令 + 校验（不自动装系统级）
    echo "── [e] 外部依赖指引（不自动安装系统级，按需执行） ──"
    local code; code=$(curl -s --max-time 6 -o /dev/null -w '%{http_code}' \
        -X POST "$LMS_CLOUD_EMBED_URL" -H 'Content-Type: application/json' \
        -d "{\"model\":\"$LMS_CLOUD_EMBED_MODEL\",\"input\":\"ping\"}" 2>/dev/null)
    if [ "$code" = "200" ]; then
        ok "embed 向量服务可达: $LMS_CLOUD_EMBED_URL（model=$LMS_CLOUD_EMBED_MODEL）"
    else
        warn "embed 不可达（HTTP $code）—— 在任意机器起 Ollama + bge-m3 后写 env.local:"
        dim "    ollama pull bge-m3 && ollama serve            # 默认 11434"
        dim "    OLLAMA_HOST=0.0.0.0:11435 ollama serve        # 本机用 11435 端口"
        dim "    校验: curl -X POST http://<host>:11435/v1/embeddings -H 'Content-Type: application/json' -d '{\"model\":\"bge-m3\",\"input\":\"ping\"}'"
        dim "    env.local: LMS_CLOUD_EMBED_URL=http://<host>:11435/v1/embeddings + VECTOR_URL 同值（LMS .env 同步）"
    fi
    if ss -tln 2>/dev/null | grep -q ":$OPENCLAW_PORT "; then
        ok "OpenClaw Gateway 监听 :$OPENCLAW_PORT"
    else
        warn "OpenClaw Gateway 未监听 :$OPENCLAW_PORT —— 安装指引（不自动装）:"
        dim "    官方安装: https://docs.openclaw.ai 按系统安装（需 node ≥18）"
        dim "    插件: git clone $GITHUB_BASE/glue-memory-injector.git → \$HOME/.openclaw/plugins/（bootstrap 已尝试 clone 到 $PLUGIN_HOME/glue-memory-injector）"
        dim "    MCP 注册 lms-memory/lms-http/shouji-memory → openclaw.json（配置片段见 SYSTEM.md「OpenClaw 安装」一节）"
    fi
    dim "    cron: 环境就绪后 bash deploy.sh cron-show 看全表（已展开），bash deploy.sh cron-install 自动合并安装"
    echo ""
    if [ "$failed" -eq 0 ]; then
        ok "bootstrap 完成（外部依赖按 [e] 指引自备）"
    else
        warn "bootstrap 完成但存在失败项（见上；多为网络问题，可重跑幂等续传）"
    fi
}

# ══════════════════════════════════════════════════════════════
# 1. 前置检测（preflight）——缺→自动修→修不了给可复制命令→不中止
#    参数: $1=autofix（1=deploy 时自动修复；0=doctor 纯检测）
#    返回: 未修复项数量（deploy 不因此中止，最后汇总）
# ══════════════════════════════════════════════════════════════
preflight() {
    local autofix="${1:-1}"
    local fails=0
    local -a fail_items=()
    repos_init

    echo "═══ [1/7] 配置中心 env.local ═══"
    if [ -f "$AGENT_OS_HOME/env.local" ]; then
        ok "env.local 存在: $AGENT_OS_HOME/env.local"
    elif [ "$autofix" = "1" ] && [ -f "$AGENT_OS_HOME/env.template" ]; then
        echo "  → 自动修复: 从 env.template 生成 env.local ..."
        if env_local_generate; then
            ok "env.local 已自动生成（A 节按标准布局填默认，非标准布局请编辑）"
        else
            fail "env.local 自动生成失败"; fails=$((fails+1)); fail_items+=("env.local 生成失败（env.template 缺失？重新 clone agent-os）")
        fi
    elif [ -f "$AGENT_OS_HOME/env.template" ]; then
        fail "env.local 缺失（可复制命令: cd \"$AGENT_OS_HOME\" && bash stack_ctl.sh setup 生成）"
        fails=$((fails+1)); fail_items+=("env.local 缺失（bash stack_ctl.sh setup 生成）")
    else
        fail "env.local 与 env.template 均缺失 —— 仓库不完整，请重新 clone agent-os"
        fails=$((fails+1)); fail_items+=("env.local 与 env.template 均缺失（重新 clone agent-os）")
    fi

    echo "═══ [2/7] 仓库目录（5 个模块） ═══"
    for v in "LIGHT_HOME:$LIGHT_HOME" "LMS_HOME:$LMS_HOME" "GLUE_HOME:$GLUE_HOME" \
             "SANDGLASS_SOURCE:$SANDGLASS_SOURCE" "ISO_SAND_HOME:$ISO_SAND_HOME" \
             "VERIFY_HOME:$VERIFY_HOME"; do
        local name="${v%%:*}" path="${v#*:}"
        if [ -d "$path" ]; then
            ok "目录 $name → $path"
        elif [ "$autofix" = "1" ] && [ "$name" != "VERIFY_HOME" ]; then
            echo "  → 自动修复: clone 缺失仓到 $path ..."
            local repo_url=""
            for item in "${REPOS[@]}"; do
                IFS='|' read -r rn ru rd <<< "$item"
                case "$name" in
                    LMS_HOME)        [ "$rn" = "living-memory-system" ] && repo_url="$ru" ;;
                    GLUE_HOME)       [ "$rn" = "memory-integration-layer" ] && repo_url="$ru" ;;
                    SANDGLASS_SOURCE) [ "$rn" = "nyx" ] && repo_url="$ru" ;;
                    LIGHT_HOME)      [ "$rn" = "edit-web.py" ] && repo_url="$ru" ;;
                esac
            done
            # LIGHT_HOME 不是单个仓（含多个），只 mkdir 不 clone
            if [ "$name" = "LIGHT_HOME" ]; then
                mkdir -p "$path" && ok "mkdir $name → $path"
            elif [ -n "$repo_url" ]; then
                repo_clone "$name" "$repo_url" "$path" || { fails=$((fails+1)); fail_items+=("目录 $name 缺失: $path（git clone $repo_url $path）"); }
            else
                mkdir -p "$path" 2>/dev/null && ok "mkdir $name → $path（目录级）"
            fi
        else
            fail "目录 $name 不存在: $path"
            fails=$((fails+1)); fail_items+=("目录 $name 不存在: $path")
        fi
    done
    # NEXSANDBASE_HOME 是数据目录：服务首次运行自动创建（G13 修正提示）
    if [ -d "$NEXSANDBASE_HOME" ]; then
        ok "数据目录 NEXSANDBASE_HOME → $NEXSANDBASE_HOME"
    else
        warn "数据目录 NEXSANDBASE_HOME 不存在: $NEXSANDBASE_HOME（首次运行自动创建；也可先 mkdir -p）"
        if [ "$autofix" = "1" ]; then mkdir -p "$NEXSANDBASE_HOME" && ok "已自动 mkdir $NEXSANDBASE_HOME"; fi
    fi
    [ -f "$SANDGLASS_SOURCE/sandglass_http_api.py" ] || { fail "沙漏源码缺 sandglass_http_api.py（clone tdx1146/nyx 到 SANDGLASS_SOURCE）"; fails=$((fails+1)); fail_items+=("沙漏源码缺 sandglass_http_api.py"); }
    [ -f "$GLUE_HOME/glue_server.py" ] || { fail "胶水层缺 glue_server.py（clone tdx1146/memory-integration-layer）"; fails=$((fails+1)); fail_items+=("胶水层缺 glue_server.py"); }
    [ -f "$VERIFY_HOME/src/verify_daemon.py" ] || { warn "玄鉴缺 src/verify_daemon.py（xuanjian/ 未检出或源码缺失；见复现缺口清单 #2；可暂缓，不影响核心链路）"; }

    echo "═══ [3/7] Python / node 运行时 ═══"
    if command -v python3 > /dev/null 2>&1; then
        local pyv; pyv=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
        if [ "$(echo "$pyv" | cut -d. -f1)" -ge 3 ] && [ "$(echo "$pyv" | cut -d. -f2)" -ge 10 ]; then
            ok "python3 $(python3 --version 2>&1 | grep -oP '\d+\.\d+\.\d+')（LMS 要求 ≥3.10，本机实测 3.11）"
            [ "$(echo "$pyv" | cut -d. -f2)" -lt 11 ] && warn "python3 为 3.$pyv，沙漏/胶水实测为 3.11，建议升级"
        else
            fail "python3 $pyv < 3.10（LMS 最低要求）"; fails=$((fails+1)); fail_items+=("python3 版本过低: $pyv（需 ≥3.10；apt install python3）")
        fi
    else
        fail "python3 未安装"; fails=$((fails+1)); fail_items+=("python3 未安装（apt install python3 python3-venv）")
    fi
    if command -v node > /dev/null 2>&1; then
        local nv; nv=$(node --version 2>&1 | tr -d 'v' | cut -d. -f1)
        [ "$nv" -ge 18 ] 2>/dev/null && ok "node $(node --version 2>&1)（≥18）" || { fail "node $(node --version 2>&1) < 18（OpenClaw 运行时要求）"; fails=$((fails+1)); fail_items+=("node < 18（需 ≥18；apt install nodejs 或官方源）"); }
    else
        fail "node 未安装（OpenClaw Gateway 运行时必需）"; fails=$((fails+1)); fail_items+=("node 未安装（apt install nodejs，OpenClaw 需 ≥18）")
    fi

    echo "═══ [4/7] LMS venv 与 .env（密钥） ═══"
    if [ -x "$LMS_HOME/.venv/bin/python" ]; then
        ok "venv 存在: $LMS_HOME/.venv/bin/python"
    elif [ "$autofix" = "1" ] && [ -d "$LMS_HOME" ]; then
        echo "  → 自动修复: 创建 venv + pip install（torch 较大，可能耗时数分钟）..."
        if ( cd "$LMS_HOME" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt > "$LOG_DIR/bootstrap-pip-lms.log" 2>&1 ); then
            ok "LMS venv + 依赖已装好"
        else
            fail "LMS venv 自动安装失败（日志: $LOG_DIR/bootstrap-pip-lms.log）"
            dim "    可复制命令: cd \"$LMS_HOME\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
            fails=$((fails+1)); fail_items+=("LMS venv 缺失: $LMS_HOME/.venv")
        fi
    else
        fail "LMS venv 缺失（可复制命令: cd \"$LMS_HOME\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt）"; fails=$((fails+1)); fail_items+=("LMS venv 缺失: $LMS_HOME/.venv")
    fi
    if [ -f "$LMS_HOME/.env" ]; then
        ok "LMS .env 存在"
        grep -q '^LMS_EMBEDDER=cloud' "$LMS_HOME/.env" 2>/dev/null && ok "LMS_EMBEDDER=cloud（HF 不可达，必须 cloud）" || warn "LMS .env 未设 LMS_EMBEDDER=cloud（否则嵌入静默降级，见 SYSTEM.md 坑 3）"
    elif [ "$autofix" = "1" ] && [ -f "$LMS_HOME/.env.example" ]; then
        cp "$LMS_HOME/.env.example" "$LMS_HOME/.env"
        warn "已自动 cp .env.example → $LMS_HOME/.env —— 请填入 DEEPSEEK_API_KEY / LMS_CLOUD_EMBED_URL 等密钥后重启 deploy"
    else
        fail "LMS .env 缺失（可复制命令: cd \"$LMS_HOME\" && cp .env.example .env 后填入 DEEPSEEK_API_KEY / LMS_CLOUD_EMBED_URL 等）"; fails=$((fails+1)); fail_items+=("LMS .env 缺失（cp .env.example .env 并填密钥）")
    fi

    echo "═══ [5/7] 外部依赖：embed 向量服务（bge-m3） ═══"
    local code; code=$(curl -s --max-time 6 -o /tmp/deploy_embed_probe.json -w '%{http_code}' \
        -X POST "$LMS_CLOUD_EMBED_URL" -H 'Content-Type: application/json' \
        -d "{\"model\":\"$LMS_CLOUD_EMBED_MODEL\",\"input\":\"ping\"}" 2>/dev/null)
    if [ "$code" = "200" ]; then
        ok "embed 服务可达: $LMS_CLOUD_EMBED_URL（model=$LMS_CLOUD_EMBED_MODEL）"
    else
        fail "embed 服务不可达: $LMS_CLOUD_EMBED_URL（HTTP $code）—— 这是 LMS/胶水感官层，缺它=静默降级"
        warn "  修复（任意机器起 Ollama + bge-m3，1024 维，暴露 /v1/embeddings）:"
        dim "    ollama pull bge-m3 && ollama serve"
        dim "    OLLAMA_HOST=0.0.0.0:11435 ollama serve"
        dim "    然后 env.local 与 LMS .env 同步 LMS_CLOUD_EMBED_URL/VECTOR_URL（或配 LMS_CLOUD_EMBED_FALLBACK_URL 隧道备用）"
        fails=$((fails+1)); fail_items+=("embed 服务不可达: $LMS_CLOUD_EMBED_URL（起 Ollama+bge-m3 后同步 env.local/LMS .env）")
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
        dim "    安装: https://docs.openclaw.ai（需 node ≥18）；插件 clone 到 $PLUGIN_HOME/；openclaw.json 片段见 SYSTEM.md"
    fi

    echo "═══ [7/7] 编辑器（落沙写入口，:${EDITOR_PORT}） ═══"
    if curl -sf --max-time 3 "http://127.0.0.1:$EDITOR_PORT/" > /dev/null 2>&1; then
        ok "编辑器 :$EDITOR_PORT 运行中"
    else
        if [ -f "$EDITOR_HOME/edit-web.py" ]; then
            warn "编辑器未运行（deploy 时会自动拉起）"
        elif [ "$autofix" = "1" ]; then
            echo "  → 自动修复: clone edit-web.py 到 $EDITOR_HOME ..."
            repo_clone "edit-web.py" "$GITHUB_BASE/edit-web.py.git" "$EDITOR_HOME" || { fails=$((fails+1)); fail_items+=("编辑器源码缺失: $EDITOR_HOME/edit-web.py"); }
        else
            fail "编辑器源码缺失: $EDITOR_HOME/edit-web.py（clone tdx1146/edit-web.py 到 EDITOR_HOME）"; fails=$((fails+1)); fail_items+=("编辑器源码缺失: $EDITOR_HOME/edit-web.py")
        fi
    fi
    # R-4（2026-08-13）：落沙 wrapper 存在性（明线写入口依赖；缺失 fail-loud）
    if [ -f "$EDITOR_HOME/sandglass_log_wrapper.py" ]; then
        ok "落沙 wrapper 就位: $EDITOR_HOME/sandglass_log_wrapper.py"
    elif [ "$autofix" = "1" ]; then
        ensure_sandglass_wrapper || { fails=$((fails+1)); fail_items+=("落沙 wrapper 缺失: $EDITOR_HOME/sandglass_log_wrapper.py（bash deploy.sh bootstrap 自动铺平）"); }
    else
        fail "落沙 wrapper 缺失: $EDITOR_HOME/sandglass_log_wrapper.py（明线落沙将静默断=失忆；bash deploy.sh bootstrap 自动铺平）"; fails=$((fails+1)); fail_items+=("落沙 wrapper 缺失: $EDITOR_HOME/sandglass_log_wrapper.py")
    fi

    echo ""
    if [ "$fails" -eq 0 ]; then
        ok "前置检测全绿"
    else
        fail "前置检测存在 ${fails} 项未修复（见上逐项；自动修复已尝试，剩余多为外部依赖/系统级）"
        echo "── 未修复项汇总（可复制命令） ──"
        local i
        for i in "${!fail_items[@]}"; do
            echo "  $((i+1)). ${fail_items[$i]}"
        done
        if [ "$autofix" = "1" ]; then
            warn "deploy 继续尝试拉起已就绪服务；修复后可重跑 bash deploy.sh（幂等）"
        fi
    fi
    return $fails
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
    # R-4（2026-08-13）：落沙 wrapper 缺失 = 明线断，拒绝静默启动（fail-loud）
    if [ ! -f "$EDITOR_HOME/sandglass_log_wrapper.py" ]; then
        fail "落沙 wrapper 缺失: $EDITOR_HOME/sandglass_log_wrapper.py —— 明线落沙将静默失败（失忆）。已拒绝启动编辑器；请先运行 bash deploy.sh bootstrap 补齐（R-4）"
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
    # R-4（2026-08-13）：落沙 wrapper 就位检查（编辑器在跑但 wrapper 缺失 = 静默失忆）
    if [ -f "$EDITOR_HOME/sandglass_log_wrapper.py" ]; then
        ok "落沙 wrapper 就位（每轮消息将写入沙漏）"
    else
        fail "落沙 wrapper 缺失: $EDITOR_HOME/sandglass_log_wrapper.py —— 编辑器在跑但落沙静默断（失忆）；先 bash deploy.sh bootstrap（R-4）"; allok=0
    fi
    local txt_tail; txt_tail=$(tail -1 "$NEXSANDBASE_HOME/sandglass.txt" 2>/dev/null | head -c 80)
    [ -n "$txt_tail" ] && ok "沙漏 txt 尾部: $txt_tail" || warn "sandglass.txt 为空或不可读（$NEXSANDBASE_HOME/sandglass.txt，新机器首次落沙后生成）"

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
    [ "$missing" -eq 0 ] && ok "crontab 全表完整" || warn "缺失条目可 bash deploy.sh cron-install 自动合并安装（幂等），或 cron-show 查看全表手动复制"
    echo ""
    # R-1（2026-08-13）：cron 指向的脚本必须真实存在（fail-loud，防静默死条目）
    verify_cron_targets || warn "存在 cron 目标缺失 —— cron-install 会拒绝安装；请先 bash deploy.sh bootstrap 接线（R-1）"
}

cron_show() {
    # R-1（2026-08-13）：先校验 cron 目标脚本存在（缺失时表格不可直接复制——fail-loud）
    if ! verify_cron_targets; then
        warn "⚠️ 下列 crontab 中指向缺失脚本的条目将是死条目 —— 请先运行 bash deploy.sh bootstrap 接线（R-1），再复制本表"
        echo ""
    fi
    # 用 env.local 实际值展开（heredoc 不加引号；路径保持引号，兼容含空格的路径）。
    # 演练实锤：旧版 `<<'EOF'` 输出字面 $LMS_HOME/$LIGHT_HOME/$AGENT_OS_HOME，
    # 照抄进 crontab 全是空变量静默失效。
    local b="$LMS_HOME/scripts/lms_backup.sh"
    local lmsctl="$LMS_HOME/scripts/lms_ctl.sh"
    local runctl="$LMS_HOME/.venv/bin/python $LMS_HOME/scripts/run_control.py"
    local pulse="$LIGHT_HOME/scripts/pulse-cron.sh"
    local watchdog="$LIGHT_HOME/scripts/session-reset-watchdog.py"
    local hcheck="$LIGHT_HOME/scripts/health-check.sh"
    cat <<EOF
# ===== 推荐 crontab 全表（已按本机 env.local 展开，可直接复制） =====
# LMS 备份三档
*/15 * * * *  $b --quick
0 * * * *     $b --hourly
30 2 * * *    $b --daily
# 开机自启（LMS 由 lms_ctl.sh 幂等拉起；全栈由 start_all.sh）
@reboot       sleep 30 && bash $lmsctl start
@reboot       sleep 45 && setsid $runctl --host 127.0.0.1 --port 8191 < /dev/null &
@reboot       sleep 20 && bash "$AGENT_OS_HOME/start_all.sh"
# 怀疑/唤醒三锁
*/10 * * * *  bash $pulse
30 23 * * *   bash "$AGENT_OS_HOME/doubt-system/night_patrol_run.sh"
*/2 * * * *   python3 $watchdog
# 自愈/巡检
*/5 * * * *   bash $hcheck
*/30 * * * *  bash "$AGENT_OS_HOME/scripts/system_health_check.sh" --cron
*/30 * * * *  bash "$AGENT_OS_HOME/scripts/contract_check.sh" --cron
*/10 * * * *  bash "$AGENT_OS_HOME/scripts/sandglass_sync.sh"
*/5 * * * *   bash "$AGENT_OS_HOME/scripts/gen_dashboard.sh"
EOF
}

# 合并安装推荐 crontab（备份→按命令关键词去重合并，幂等；G6「部署者不需要手抄」落地）
cron_install() {
    # R-1（2026-08-13）：安装前校验 cron 目标脚本存在（缺失=装了也是死条目，拒绝安装，fail-loud）
    if ! verify_cron_targets; then
        fail "cron 目标脚本缺失（见上）—— 拒绝安装死条目。请先 bash deploy.sh bootstrap 接线（R-1）后重试"
        return 1
    fi
    local now; now=$(date '+%Y%m%d-%H%M%S')
    local bak="$HOME/.crontab.bak-$now"
    crontab -l > "$bak" 2>/dev/null || true
    echo "已备份现有 crontab → $bak"
    local tmp; tmp=$(mktemp)
    local skip=0 added=0
    local existing; existing=$(crontab -l 2>/dev/null || true)
    # 去重键 = 行内最后一个脚本路径（xxx.sh/xxx.py），忽略重定向/引号差异；
    # 已有条目带 >>log 2>&1 后缀也能正确判重（2026-08-13 修复：曾按行尾 token 判重导致重复添加）
    key_of() { printf '%s' "$1" | tr -d '"' | grep -oE '[^ ]+\.(sh|py)' | tail -1; }
    local line kw
    while IFS= read -r line; do
        case "$line" in \#*|"") continue ;; esac
        kw=$(key_of "$line")
        [ -z "$kw" ] && { echo "  跳过(无脚本路径): $line"; continue; }
        if printf '%s\n' "$existing" | grep -qF "$kw"; then
            echo "  跳过已存在: $kw"; skip=$((skip+1)); continue
        fi
        echo "$line" >> "$tmp"; added=$((added+1))
    done < <(cron_show | sed '1d')   # 去掉首行注释标题
    if [ "$added" -gt 0 ]; then
        { printf '%s\n' "$existing"; cat "$tmp"; } | crontab -
        echo "✅ 新增 $added 条（跳过 $skip 条已存在）—— 注意 @reboot 条目需重新登录/重启才生效"
    else
        echo "✅ 无新增（$skip 条已存在，幂等）"
    fi
    rm -f "$tmp"
}

# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════
case "$CMD" in
  doctor|preflight)
    preflight 0; exit $?
    ;;
  bootstrap)
    bootstrap; exit $?
    ;;
  cron)
    cron_check; exit 0
    ;;
  cron-show)
    cron_show; exit 0
    ;;
  cron-install)
    cron_install; exit $?
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
    # 1. bootstrap：环境安装（幂等；clone/venv/.env/数据目录/外部依赖指引）
    bootstrap
    echo ""
    # 2. 前置检测（缺→自动修→修不了给可复制命令→不中止；失败项最后汇总）
    preflight 1
    echo ""
    # 3. 按依赖顺序拉起 6 服务（stack_ctl.sh 内部已按 沙漏→LMS→胶水→总线→玄鉴 顺序 + 幂等）
    echo "── 拉起 6 服务栈（依赖顺序，幂等） ──"
    bash "$AGENT_OS_HOME/stack_ctl.sh" start
    echo ""
    # 4. 拉起编辑器（落沙写入口）
    start_editor
    echo ""
    # 5. 每步健康验证
    verify_services
    VRC_=$?
    echo ""
    # 6. crontab 检查（只读提示）
    cron_check
    echo ""
    echo "────────────────────────────────────────────────"
    if [ "$VRC_" -eq 0 ]; then
        ok "一键部署完成 —— 核心链路全绿；日常查健康: bash deploy.sh status / bash scripts/system_health_check.sh"
    else
        fail "部署完成但存在红项（见上）；修复后重跑 bash deploy.sh（幂等）"
        dim "  未就绪项多为外部依赖（embed/OpenClaw/cron），按 [e]/[5/7]/[6/7] 指引补齐后重跑"
    fi
    exit $VRC_
    ;;
  *)
    echo "用法: bash deploy.sh [deploy|bootstrap|doctor|status|stop|verify|cron|cron-show|cron-install]"
    echo "  deploy        完整部署（bootstrap + 自动修复 + 拉起；默认，幂等）"
    echo "  bootstrap     只做环境安装（clone 6 仓/venv/.env/数据目录/外部依赖指引）"
    echo "  doctor        只做前置检测（不自动修复、不启动）"
    echo "  status        全栈状态汇总"
    echo "  stop          停止 6 服务栈"
    echo "  verify        部署后深度验证"
    echo "  cron          检查 crontab 缺失条目"
    echo "  cron-show     打印推荐 crontab 全表（已按 env.local 展开）"
    echo "  cron-install  合并安装推荐 crontab（备份→去重→幂等）"
    exit 1
    ;;
esac
