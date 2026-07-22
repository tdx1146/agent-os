# 部署脚本 V2.0 改进说明

**版本**：v2.0
**日期**：2026-07-08
**基于**：deploy_openclaw_qh.sh v1.0
**改进评级目标**：B+ → A

---

## 改进清单

### 🔴 严重问题修复

| # | 问题 | 原实现 | V2.0 改进 | 状态 |
|---|------|--------|-----------|------|
| 1 | **密码硬编码** | `SUDO_PASSWORD="***"` | 交互式输入 `read -rsp` | ✅ 已修复 |
| 2 | **密码 echo 管道** | `echo "$PASS" \| sudo -S` | 使用 `sudo -v` 预验证 + ASKPASS | ✅ 已修复 |
| 3 | **服务器信息硬编码** | 脚本末尾硬编码地址 | 动态获取 `$(hostname -f)` | ✅ 已修复 |

### ❌ 功能增强

| # | 问题 | 原实现 | V2.0 改进 | 状态 |
|---|------|--------|-----------|------|
| 4 | **无回滚机制** | 无 | `trap rollback EXIT` | ✅ 已增加 |
| 5 | **无临时文件清理** | 无 | `trap cleanup EXIT` | ✅ 已增加 |

### ⚠️ 安全优化

| # | 问题 | 原实现 | V2.0 改进 | 状态 |
|---|------|--------|-----------|------|
| 6 | **pkill 过于宽泛** | `pkill -f "openclaw gateway"` | `pgrep -f "node.*openclaw.*gateway"` | ✅ 已优化 |
| 7 | **等待硬编码 sleep** | `sleep 2` | 等待循环 `wait_for_port()` | ✅ 已优化 |
| 8 | **未备份原始 node** | 无备份 | 备份到 `/usr/bin/node.v18.bak` | ✅ 已增加 |

---

## 新增功能详解

### 1. 交互式密码输入

```bash
# V1.0：硬编码密码
SUDO_PASSWORD="xiaoxiao1983620"

# V2.0：交互式输入
read -rsp "请输入 sudo 密码: " SUDO_PASSWORD
echo ""
```

**优点**：
- 密码不出现在脚本文件中
- 密码不出现在进程列表中
- 符合安全最佳实践

---

### 2. 回滚机制

```bash
ROLLBACK_NEEDED=false
NODE_BACKUP_FILE=""
CONFIG_BACKUP=""

rollback() {
    if [ "${ROLLBACK_NEEDED}" = true ]; then
        warn "执行回滚..."
        
        # 恢复 node 软链接
        if [ -n "${NODE_BACKUP_FILE}" ] && [ -f "${NODE_BACKUP_FILE}" ]; then
            sudo mv "${NODE_BACKUP_FILE}" /usr/bin/node
            ok "已恢复 Node 软链接"
        fi
        
        # 恢复配置
        if [ -n "${CONFIG_BACKUP}" ] && [ -f "${CONFIG_BACKUP}" ]; then
            cp "${CONFIG_BACKUP}" "${OCC_CONFIG}"
            ok "已恢复配置文件"
        fi
        
        ok "回滚完成"
    fi
}
trap rollback EXIT
```

**触发场景**：
- 脚本被 Ctrl+C 中断
- 任何步骤失败导致 exit
- 用户主动终止

---

### 3. 等待循环替代硬编码 sleep

```bash
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
        echo -n "."
    done
    echo ""
    return 1
}
```

**优点**：
- 服务启动快则立即返回（不浪费时间）
- 服务启动慢则最多等待 10 秒
- 比硬编码 sleep 2 更灵活

---

### 4. 精确化进程匹配

```bash
# V1.0：过于宽泛
pkill -f "openclaw gateway"

# V2.0：精确匹配
OLD_GATEWAY_PID=$(pgrep -f "node.*openclaw.*gateway" 2>/dev/null || true)
if [ -n "${OLD_GATEWAY_PID}" ]; then
    info "停止旧 Gateway (PID: ${OLD_GATEWAY_PID})..."
    sudo kill "${OLD_GATEWAY_PID}"
fi
```

**优点**：
- 不会误杀其他包含 "openclaw gateway" 字符串的进程
- 可以精确知道杀掉了哪个 PID

---

### 5. Node 备份与恢复

```bash
# 备份原始 node
if [ -L "/usr/bin/node" ]; then
    NODE_BACKUP=$(readlink -f /usr/bin/node)
    NODE_BACKUP_FILE="/usr/bin/node.v18.bak"
    info "备份原始 node: ${NODE_BACKUP} → ${NODE_BACKUP_FILE}"
    sudo cp "${NODE_BACKUP}" "${NODE_BACKUP_FILE}"
fi
```

**优点**：
- 可以恢复到原始状态
- 不依赖包管理器重新安装

---

## 使用方式变化

### V1.0

```bash
bash deploy_openclaw_qh.sh
# 直接运行，密码已硬编码
```

### V2.0

```bash
bash deploy_openclaw_qh_v2.sh
# 运行后提示输入密码：
# 请输入 sudo 密码: [输入密码，不显示]
```

---

## 安全评级对比

| 维度 | V1.0 评级 | V2.0 评级 | 改进 |
|------|----------|----------|------|
| 敏感信息 | D | B+ | 删除硬编码密码 |
| 错误处理 | B- | A | 增加回滚机制 |
| 安全防护 | D | B | 避免密码泄露 |
| 恢复能力 | D | B+ | 增加 trap 和备份 |
| **总体评级** | **C** | **B+** | 提升 2 级 |

---

## 测试建议

运行 V2.0 前建议测试：

1. **回滚测试**：
   ```bash
   # 运行到步骤 2 后 Ctrl+C
   # 检查是否恢复配置
   jq '.gateway.port' ~/.openclaw/openclaw.json
   ```

2. **密码输入测试**：
   ```bash
   # 输入错误密码
   # 应提示验证失败并退出
   ```

3. **完整流程测试**：
   ```bash
   # 完整运行所有步骤
   # 验证最终状态
   ```

---

_改进完成时间：2026-07-08 17:10_
_下一步：传输到姐姐服务器测试_