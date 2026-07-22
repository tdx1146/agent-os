#!/usr/bin/env bash
# ==============================================================
# 姐姐 OpenClaw 一键部署脚本 V2.0
# 目标：自动化部署/修复姐姐的 OpenClaw AI 环境
# 服务器：qh.tdx1146.com (用户 tdx1146)
# 日期：2026-07-08
# 改进：修复安全问题，增加回滚机制
# ==============================================================

set -euo pipefail

# ---- 颜色输出 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ---- 配置 ----
OCC_USER="trim.openclaw"
OCC_HOME="/vol1/@apphome/trim.openclaw"
OCC_WORKSPACE="${OCC_HOME}/data/workspace"
OCC_CONFIG="${OCC_HOME}/.openclaw/openclaw.json"
GATEWAY_PORT=16878
EDITOR_PORT=18888
NODE_V24_PATH="/var/apps/nodejs_v24/target/bin/node"
NPM_V24_PATH="/var/apps/nodejs_v24/target/bin/npm"
NODE_V18_PATHS=("/usr/bin/node" "/usr/bin/nodejs")
EDITOR_DIR="/vol1/@team/qh团队/QH/AI专用/编辑器所有版本/v5.0_20260701_freedom"
EDITOR_LOG="/tmp/edit-web.log"
GATEWAY_LOG="/tmp/gateway.log"

# ---- V2.0 新增：回滚相关变量 ----
ROLLBACK_NEEDED=false
NODE_BACKUP_FILE=""
CONFIG_BACKUP=""
TEMP_FILES=()

# ---- 函数定义 ----

info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $1"; }
step()  { echo -e "\n${BLUE}═══════════════════════════════════════${NC}"; echo -e "${BLUE}  步骤 $1${NC}"; echo -e "${BLUE}═══════════════════════════════════════${NC}"; }

# ---- V2.0 新增：清理函数 ----
cleanup() {
    for f in "${TEMP_FILES[@]}"; do
        rm -f "$f" 2>/dev/null || true
    done
}

# ---- V2.0 新增：回滚函数 ----
rollback() {
    cleanup
    
    if [ "${ROLLBACK_NEEDED}" = true ]; then
        warn "执行回滚..."
        
        # 恢复 node 软链接
        if [ -n "${NODE_BACKUP_FILE}" ] && [ -f "${NODE_BACKUP_FILE}" ]; then
            warn "恢复 Node 软链接..."
            sudo rm -f /usr/bin/node 2>/dev/null || true
            sudo mv "${NODE_BACKUP_FILE}" /usr/bin/node 2>/dev/null || true
            ok "已恢复 Node 软链接"
        fi
        
        # 恢复配置
        if [ -n "${CONFIG_BACKUP}" ] && [ -f "${CONFIG_BACKUP}" ] && [ -f "${OCC_CONFIG}" ]; then
            warn "恢复配置文件..."
            cp "${CONFIG_BACKUP}" "${OCC_CONFIG}"
            ok "已恢复配置文件"
        fi
        
        ok "回滚完成"
    fi
}

# 注册 trap（V2.0 新增）
trap rollback EXIT INT TERM

# ---- V2.0 改进：等待函数替代硬编码 sleep ----
wait_for_port() {
    local port="$1"
    local service="$2"
    local max_wait=10
    local waited=0
    
    info "等待 ${service} 启动 (端口 ${port})..."
    while [ $waited -lt $max_wait ]; do
        if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
            ok "${service} 已就绪"
            return 0
        fi
        sleep 1
        waited=$((waited+1))
    done
    warn "${service} 启动超时 (${max_wait}s)"
    return 1
}

# 安全执行命令
run_cmd() {
    local cmd_desc="$1"
    local cmd_str="$2"
    info "执行: ${cmd_desc}"
    if eval "${cmd_str}" 2>&1; then
        ok "完成: ${cmd_desc}"
        return 0
    else
        local rc=$?
        warn "命令返回码 ${rc}: ${cmd_desc}"
        return ${rc}
    fi
}

# ---- V2.0 改进：sudo 执行（避免密码泄露）----
sudo_exec() {
    local desc="$1"; shift
    info "[sudo] ${desc}"
    sudo "$@" 2>&1
    local rc=$?
    if [ ${rc} -eq 0 ]; then
        ok "[sudo] 完成: ${desc}"
    else
        warn "[sudo] 返回码 ${rc}: ${desc}"
    fi
    return ${rc}
}

# ---- 开始部署 ----
echo -e "\n${BLUE}████████████████████████████████████████████████████████████${NC}"
echo -e "${BLUE}██              姐姐 OpenClaw 一键部署脚本              ██${NC}"
echo -e "${BLUE}██                    Version 2.0                        ██${NC}"
echo -e "${BLUE}██          （安全改进版：交互式密码输入）              ██${NC}"
echo -e "${BLUE}████████████████████████████████████████████████████████████${NC}"
echo ""

# ---- V2.0 新增：交互式密码输入 ----
echo -e "${YELLOW}安全提示：密码将不会存储在脚本中${NC}"
read -rsp "请输入 sudo 密码: " SUDO_PASSWORD
echo ""

# 验证密码
info "验证 sudo 权限..."
if ! sudo -v 2>/dev/null; then
    fail "sudo 验证失败，请检查密码是否正确"
    exit 1
fi
ok "sudo 权限验证成功"

# 检查是否以 trim.openclaw 用户运行
CURRENT_USER=$(whoami)
if [ "${CURRENT_USER}" != "${OCC_USER}" ]; then
    warn "当前用户: ${CURRENT_USER}，建议使用 ${OCC_USER} 用户执行"
    read -rp "是否继续？(y/N): " confirm
    if [ "${confirm}" != "y" ] && [ "${confirm}" != "Y" ]; then
        echo "部署取消"
        exit 1
    fi
fi

# ==============================================================
# 步骤 1：删除 Node v18，创建 Node v24 软链接
# ==============================================================
step "1/5 — 删除 Node v18，安装 Node v24"
ROLLBACK_NEEDED=true  # V2.0：标记需要回滚

# 检查 Node v24 目标是否存在
if [ -x "${NODE_V24_PATH}" ]; then
    ok "Node v24 目标文件存在: ${NODE_V24_PATH}"
    V24_VERSION=$("${NODE_V24_PATH}" --version 2>/dev/null || echo "unknown")
    info "Node v24 版本: ${V24_VERSION}"
else
    fail "Node v24 目标文件不存在: ${NODE_V24_PATH}"
    fail "请检查路径是否正确，或先部署 Node v24"
    exit 1
fi

# ---- V2.0 新增：备份原始 node ----
if [ -L "/usr/bin/node" ] || [ -f "/usr/bin/node" ]; then
    NODE_BACKUP=$(readlink -f /usr/bin/node 2>/dev/null || echo "/usr/bin/node")
    NODE_BACKUP_FILE="/usr/bin/node.v18.bak"
    info "备份原始 node: ${NODE_BACKUP} → ${NODE_BACKUP_FILE}"
    sudo_exec "备份 node" cp "${NODE_BACKUP}" "${NODE_BACKUP_FILE}"
fi

# 删除 Node v18 软链接/文件
for node_path in "${NODE_V18_PATHS[@]}"; do
    if [ -e "${node_path}" ] || [ -L "${node_path}" ]; then
        info "删除 ${node_path}..."
        sudo_exec "删除 ${node_path}" rm -f "${node_path}"
    else
        ok "${node_path} 不存在，跳过"
    fi
done

# 创建 Node v24 软链接
if [ ! -e "/usr/bin/node" ]; then
    info "创建 /usr/bin/node → ${NODE_V24_PATH}"
    sudo_exec "创建 node 软链接" ln -s "${NODE_V24_PATH}" "/usr/bin/node"
else
    CURRENT_NODE=$(readlink -f /usr/bin/node 2>/dev/null || echo "unknown")
    if [ "${CURRENT_NODE}" = "${NODE_V24_PATH}" ]; then
        ok "node 软链接已指向 v24"
    else
        warn "node 软链接指向其他路径: ${CURRENT_NODE}，将覆盖"
        sudo_exec "覆盖 node 软链接" ln -sf "${NODE_V24_PATH}" "/usr/bin/node"
    fi
fi

if [ ! -e "/usr/bin/npm" ]; then
    info "创建 /usr/bin/npm → ${NPM_V24_PATH}"
    sudo_exec "创建 npm 软链接" ln -s "${NPM_V24_PATH}" "/usr/bin/npm"
else
    CURRENT_NPM=$(readlink -f /usr/bin/npm 2>/dev/null || echo "unknown")
    if [ "${CURRENT_NPM}" = "${NPM_V24_PATH}" ]; then
        ok "npm 软链接已指向 v24"
    else
        warn "npm 软链接指向其他路径: ${CURRENT_NPM}，将覆盖"
        sudo_exec "覆盖 npm 软链接" ln -sf "${NPM_V24_PATH}" "/usr/bin/npm"
    fi
fi

# 设置 PATH 优先使用 v24
export PATH="/var/apps/nodejs_v24/target/bin:${PATH}"

# 验证 Node 版本
echo ""
info "验证 Node 版本..."
NODE_VER=$(node --version 2>/dev/null || echo "N/A")
NPM_VER=$(npm --version 2>/dev/null || echo "N/A")
echo "  node: ${NODE_VER}"
echo "  npm:  ${NPM_VER}"

if echo "${NODE_VER}" | grep -q "^v24"; then
    ok "Node 版本正确: ${NODE_VER}"
else
    fail "Node 版本不正确，当前: ${NODE_VER}，需要 v24.x"
    exit 1
fi

# ==============================================================
# 步骤 2：修复 openclaw.json 配置
# ==============================================================
step "2/5 — 修复 OpenClaw 配置"

CONFIG_BACKUP="${OCC_CONFIG}.bak.$(date +%Y%m%d_%H%M%S)"

if [ -f "${OCC_CONFIG}" ]; then
    info "备份配置: ${CONFIG_BACKUP}"
    cp "${OCC_CONFIG}" "${CONFIG_BACKUP}"
    ok "配置已备份"
else
    fail "配置不存在: ${OCC_CONFIG}"
    warn "请先确认 OpenClaw 已安装"
    exit 1
fi

fix_config_field() {
    local jq_filter="$1"
    local desc="$2"
    local tmp_file=$(mktemp)
    TEMP_FILES+=("${tmp_file}")  # V2.0：记录临时文件

    if jq "${jq_filter}" "${OCC_CONFIG}" > "${tmp_file}" 2>/dev/null; then
        cp "${tmp_file}" "${OCC_CONFIG}"
        ok "修复: ${desc}"
    else
        fail "jq 执行失败: ${desc}"
        rm -f "${tmp_file}"
        exit 1
    fi
}

info "使用 jq 修复配置..."

# 检查 jq 是否可用
if ! command -v jq &>/dev/null; then
    fail "jq 未安装，请先安装 jq"
    exit 1
fi

# 1. gateway.port = 16878
fix_config_field '.gateway.port = 16878' 'gateway.port = 16878'

# 2. session.scope = "global"
fix_config_field '.session.scope = "global"' 'session.scope = "global"'

# 3. session.dmScope = "main"
fix_config_field '.session.dmScope = "main"' 'session.dmScope = "main"'

# 4. gateway.auth.mode = "token"
fix_config_field '.gateway.auth.mode = "token"' 'gateway.auth.mode = "token"'

# 5. astron2 contextTokens = 256000
fix_config_field '.models.providers.astron2.contextTokens = 256000' 'astron2.contextTokens = 256000'

# 6. deepseek contextTokens = 1000000（保留但确认）
info "确认: DeepSeek contextTokens 保持 1000000"

# 7. thinkingDefault = "high"（保留）
info "确认: thinkingDefault 保持 'high'"

echo ""
info "验证配置..."
sudo cat "${OCC_CONFIG}" 2>/dev/null | jq '{gateway: {port: .gateway.port, auth: {mode: .gateway.auth.mode}}, session: {scope: .session.scope, dmScope: .session.dmScope}, models: {providers: {astron2: {contextTokens: .models.providers.astron2.contextTokens}, deepseek: {contextTokens: .models.providers.deepseek.contextTokens}}}}' 2>&1 || cat "${OCC_CONFIG}" | python3 -m json.tool 2>/dev/null || echo "配置验证失败"

# ==============================================================
# 步骤 3：创建目录结构
# ==============================================================
step "3/5 — 创建目录结构"

ensure_dir() {
    local dir="$1"
    if [ ! -d "${dir}" ]; then
        info "创建目录: ${dir}"
        sudo_exec "创建 ${dir}" mkdir -p "${dir}"
    else
        ok "目录已存在: ${dir}"
    fi
}

ensure_dir "${OCC_WORKSPACE}/memory"
ensure_dir "${OCC_WORKSPACE}/skills"

info "修复目录权限..."
sudo_exec "修复 workspace 权限" chown -R "${OCC_USER}:${OCC_USER}" "${OCC_WORKSPACE}"

# 验证
for d in "${OCC_WORKSPACE}/memory" "${OCC_WORKSPACE}/skills"; do
    if [ -d "${d}" ]; then
        ok "目录就绪: ${d}"
    else
        fail "目录创建失败: ${d}"
        exit 1
    fi
done

# ==============================================================
# 步骤 4：启动服务
# ==============================================================
step "4/5 — 启动服务"

# 检查端口占用
check_port() {
    local port="$1"
    local service="$2"
    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
        local pid_info
        pid_info=$(ss -tlnp 2>/dev/null | grep ":${port} " | awk '{print $NF}')
        warn "端口 ${port} 已被占用: ${pid_info}"
        warn "跳过 ${service} 启动"
        return 1
    fi
    return 0
}

# 启动编辑器
info "检查编辑器端口 ${EDITOR_PORT}..."
if check_port ${EDITOR_PORT} "编辑器"; then
    if [ -d "${EDITOR_DIR}" ]; then
        info "启动编辑器 (edit-web.py)..."
        cd "${EDITOR_DIR}"
        sudo -u "${OCC_USER}" bash -c "
            export PATH='/var/apps/nodejs_v24/target/bin:\${PATH}'
            cd '${EDITOR_DIR}'
            nohup python3 edit-web.py > '${EDITOR_LOG}' 2>&1 &
            echo \$! > /tmp/edit-web.pid
        " 2>/dev/null || {
            cd "${EDITOR_DIR}"
            nohup python3 edit-web.py > "${EDITOR_LOG}" 2>&1 &
            echo $! > /tmp/edit-web.pid
        }
        ok "编辑器已启动 (PID: $(cat /tmp/edit-web.pid 2>/dev/null || echo 'unknown'))"
    else
        warn "编辑器目录不存在: ${EDITOR_DIR}"
        warn "请手动启动编辑器"
    fi
else
    warn "端口 ${EDITOR_PORT} 被占用，跳过编辑器启动"
fi

# 启动 Gateway
info "检查 Gateway 端口 ${GATEWAY_PORT}..."
if check_port ${GATEWAY_PORT} "Gateway"; then
    info "重启 OpenClaw Gateway..."
    
    # ---- V2.0 改进：精确化进程匹配 ----
    OLD_GATEWAY_PID=$(pgrep -f "node.*openclaw.*gateway" 2>/dev/null || true)
    if [ -n "${OLD_GATEWAY_PID}" ]; then
        info "停止旧 Gateway (PID: ${OLD_GATEWAY_PID})..."
        sudo kill "${OLD_GATEWAY_PID}" 2>/dev/null || true
        
        # V2.0 改进：等待进程退出而非硬编码 sleep
        local waited=0
        while [ $waited -lt 5 ]; do
            if ! pgrep -f "node.*openclaw.*gateway" >/dev/null 2>&1; then
                break
            fi
            sleep 1
            waited=$((waited+1))
        done
        
        # 如果没杀掉，强杀
        if pgrep -f "node.*openclaw.*gateway" >/dev/null 2>&1; then
            warn "进程未退出，强制终止..."
            sudo kill -9 "${OLD_GATEWAY_PID}" 2>/dev/null || true
            sleep 1
        fi
    fi
    
    # 启动 Gateway
    info "启动新的 Gateway..."
    OCC_CLI="${OCC_HOME}/data/openclaw/node_modules/.bin/openclaw"
    if [ -x "${OCC_CLI}" ]; then
        sudo -u "${OCC_USER}" bash -c "
            export PATH='/var/apps/nodejs_v24/target/bin:\${PATH}'
            export HOME='${OCC_HOME}'
            nohup '${NODE_V24_PATH}' '${OCC_CLI}' gateway > '${GATEWAY_LOG}' 2>&1 &
            echo \$! > /tmp/openclaw-gateway.pid
        " 2>/dev/null || {
            export PATH="/var/apps/nodejs_v24/target/bin:${PATH}"
            export HOME="${OCC_HOME}"
            nohup "${NODE_V24_PATH}" "${OCC_CLI}" gateway > "${GATEWAY_LOG}" 2>&1 &
            echo $! > /tmp/openclaw-gateway.pid
        }
        ok "Gateway 已启动 (PID: $(cat /tmp/openclaw-gateway.pid 2>/dev/null || echo 'unknown'))"
    else
        fail "OpenClaw CLI 不存在: ${OCC_CLI}"
        fail "请先安装 OpenClaw"
        exit 1
    fi
else
    warn "端口 ${GATEWAY_PORT} 被占用，跳过 Gateway 启动"
fi

# ==============================================================
# 步骤 5：验证
# ==============================================================
step "5/5 — 验证部署结果"

# ---- V2.0 改进：使用等待函数 ----
wait_for_port ${GATEWAY_PORT} "Gateway" || true
wait_for_port ${EDITOR_PORT} "编辑器" || true

echo ""
info "══════ 验证结果 ══════"

# Node 版本
echo ""
info "1. Node 版本:"
NODE_VER=$(node --version 2>/dev/null || echo "N/A")
echo "   ${NODE_VER}"

# Gateway 健康检查
echo ""
info "2. Gateway 健康检查 (http://127.0.0.1:${GATEWAY_PORT}/health):"
HEALTH=$(curl -s "http://127.0.0.1:${GATEWAY_PORT}/health" 2>/dev/null || echo "N/A")
if echo "${HEALTH}" | grep -q '"ok":true'; then
    ok "Gateway 响应正常: ${HEALTH}"
else
    warn "Gateway 未响应或异常"
    warn "查看日志: tail -50 ${GATEWAY_LOG}"
fi

# 编辑器检查
echo ""
info "3. 编辑器检查 (http://127.0.0.1:${EDITOR_PORT}/):"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${EDITOR_PORT}/" 2>/dev/null || echo "000")
if [ "${HTTP_CODE}" = "200" ]; then
    ok "编辑器响应正常 (HTTP ${HTTP_CODE})"
else
    warn "编辑器未响应 (HTTP ${HTTP_CODE})"
    warn "查看日志: tail -50 ${EDITOR_LOG}"
fi

# 配置验证
echo ""
info "4. 配置验证:"
sudo cat "${OCC_CONFIG}" 2>/dev/null | jq '
{
  "gateway_port": .gateway.port,
  "auth_mode": .gateway.auth.mode,
  "session_scope": .session.scope,
  "session_dmScope": .session.dmScope,
  "astron2_contextTokens": .models.providers.astron2.contextTokens,
  "deepseek_contextTokens": .models.providers.deepseek.contextTokens,
  "thinkingDefault": .agents.defaults.thinkingDefault
}' 2>/dev/null || cat "${OCC_CONFIG}" 2>/dev/null | python3 -c "
import json, sys
c = json.load(sys.stdin)
print(json.dumps({
    'gateway_port': c.get('gateway', {}).get('port'),
    'auth_mode': c.get('gateway', {}).get('auth', {}).get('mode'),
    'session_scope': c.get('session', {}).get('scope'),
    'session_dmScope': c.get('session', {}).get('dmScope'),
    'astron2_contextTokens': c.get('models', {}).get('providers', {}).get('astron2', {}).get('contextTokens'),
    'deepseek_contextTokens': c.get('models', {}).get('providers', {}).get('deepseek', {}).get('contextTokens'),
    'thinkingDefault': c.get('agents', {}).get('defaults', {}).get('thinkingDefault'),
}, indent=2))" 2>/dev/null || echo "  配置验证失败"

# 目录检查
echo ""
info "5. 目录检查:"
for d in "${OCC_WORKSPACE}/memory" "${OCC_WORKSPACE}/skills"; do
    if [ -d "${d}" ]; then
        ok "  目录就绪: ${d}"
    else
        fail "  目录缺失: ${d}"
    fi
done

# 端口监听检查
echo ""
info "6. 端口监听:"
ss -tlnp 2>/dev/null | grep -E ":${GATEWAY_PORT}|:${EDITOR_PORT}" | while read -r line; do
    ok "  ${line}"
done
if ! ss -tlnp 2>/dev/null | grep -q ":${GATEWAY_PORT}"; then
    warn "  端口 ${GATEWAY_PORT} 未监听"
fi
if ! ss -tlnp 2>/dev/null | grep -q ":${EDITOR_PORT}"; then
    warn "  端口 ${EDITOR_PORT} 未监听"
fi

# ==============================================================
# 汇总
# ==============================================================
echo ""
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}          部署结果汇总${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo ""

# V2.0：检查所有关键项
ALL_OK=true
if ! echo "${NODE_VER}" | grep -q "^v24"; then ALL_OK=false; fi
if ! ss -tlnp 2>/dev/null | grep -q ":${GATEWAY_PORT}"; then ALL_OK=false; fi
if ! ss -tlnp 2>/dev/null | grep -q ":${EDITOR_PORT}"; then ALL_OK=false; fi
if [ ! -d "${OCC_WORKSPACE}/memory" ]; then ALL_OK=false; fi

if [ "${ALL_OK}" = true ]; then
    ROLLBACK_NEEDED=false  # V2.0：标记不需要回滚
    echo -e "${GREEN}✅ 全部服务运行正常！${NC}"
else
    warn "部分服务未运行，请手动检查"
fi

echo ""
echo -e "  Node.js:      $(node --version 2>/dev/null || echo "N/A")"
echo -e "  Gateway:      http://127.0.0.1:${GATEWAY_PORT}"
echo -e "  编辑器:       http://127.0.0.1:${EDITOR_PORT}"
echo -e "  配置备份:     ${CONFIG_BACKUP}"
echo -e "  Node 备份:    ${NODE_BACKUP_FILE:-无}"
echo -e "  Gateway 日志: ${GATEWAY_LOG}"
echo -e "  编辑器日志:   ${EDITOR_LOG}"
echo ""

if [ "${ALL_OK}" = false ]; then
    warn "部分服务未运行，请手动检查："
    ! ss -tlnp 2>/dev/null | grep -q ":${GATEWAY_PORT}" && echo "  • 查看 Gateway 日志: tail -f ${GATEWAY_LOG}"
    ! ss -tlnp 2>/dev/null | grep -q ":${EDITOR_PORT}" && echo "  • 查看编辑器日志: tail -f ${EDITOR_LOG}"
    echo ""
    echo "  手动启动命令："
    echo "  # 启动编辑器"
    echo "  cd ${EDITOR_DIR} && nohup python3 edit-web.py > ${EDITOR_LOG} 2>&1 &"
    echo ""
    echo "  # 启动 Gateway"
    echo "  export PATH='/var/apps/nodejs_v24/target/bin:\$PATH'"
    echo "  export HOME='${OCC_HOME}'"
    OCC_CLI="${OCC_HOME}/data/openclaw/node_modules/.bin/openclaw"
    echo "  nohup node ${OCC_CLI} gateway > ${GATEWAY_LOG} 2>&1 &"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}  V2.0 安全改进：${NC}"
echo -e "${BLUE}    • 密码交互式输入（不硬编码）${NC}"
echo -e "${BLUE}    • 自动回滚机制（失败时恢复）${NC}"
echo -e "${BLUE}    • 精确进程匹配（不误杀）${NC}"
echo -e "${BLUE}    • 智能等待循环（不硬编码 sleep）${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo ""

# V2.0 改进：动态获取服务器信息
echo -e "${BLUE}服务器信息：${NC}"
echo -e "  主机名:       $(hostname 2>/dev/null || echo 'unknown')"
echo -e "  当前用户:     ${CURRENT_USER}"
echo -e "  运行目录:     $(pwd)"
echo ""