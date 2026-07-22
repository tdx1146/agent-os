# 部署脚本安全审计报告

**审计对象**：`deploy_openclaw_qh.sh`  
**脚本版本**：Version 1.0（2026-07-08）  
**审计时间**：2026-07-08 16:23  
**文件大小**：~17KB，153 行可执行逻辑（函数+主流程）  
**审计人**：DeepSeek 子代理（独立审查）

---

## 总体评级：**C**（不安全可运行，存在严重风险）

| 维度 | 评分 | 说明 |
|------|------|------|
| 代码质量 | B | 结构清晰、函数拆分合理、颜色输出友好 |
| 错误处理 | B- | 有 `set -euo pipefail`，但无回滚机制 |
| 敏感信息 | **D** | 密码明文硬编码，可被任何能读文件的进程窃取 |
| 安全防护 | **D** | 无任何用户确认门禁，无权限最小化，无审计日志 |
| 恢复能力 | **D** | 无回滚机制，出错后系统处于不一致状态 |
| 系统影响 | **C** | 可以安全运行，但硬编码密码和 sudo 滥用是定时炸弹 |

---

## 详细检查项

### 1. Node v18 删除安全性 — ⚠️

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 先备份原文件 | ❌ | **没有备份 node 原始文件**。删除的是系统软链接（/usr/bin/node），备份原始目标文件 `readlink -f /usr/bin/node` 可以帮恢复 |
| 删除逻辑安全 | ✅ | 只删 `/usr/bin/node` 和 `/usr/bin/nodejs`，路径明确且不含通配符，不会误删 |
| 软链接创建正确 | ✅ | 使用 `ln -sf` 强制覆盖，存在重复创建时的保护逻辑（检查是否已指向v24） |
| 有验证步骤 | ✅ | 删除后验证 `node --version` 是否为 v24，版本不对则 exit 1 |

**问题**：删除前未备份 `/usr/bin/node` 的原始目标（可能指向系统包管理器的 nodejs，恢复时需要重新 `apt install`）。但软链接本身不影响系统预装包，风险较低。

**改进建议**：
```bash
# 删除前先备份
if [ -L "/usr/bin/node" ] || [ -f "/usr/bin/node" ]; then
    NODE_BACKUP=$(readlink -f /usr/bin/node 2>/dev/null || echo "/usr/bin/node")
    info "备份原始 node: ${NODE_BACKUP}"
    echo "${SUDO_PASSWORD}" | sudo -S cp "${NODE_BACKUP}" "/usr/bin/node.v18.bak"
fi
```

---

### 2. 配置修改安全性 — ⚠️

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 先备份 openclaw.json | ✅ | `cp "${OCC_CONFIG}" "${CONFIG_BACKUP}"` — 带时间戳，好 |
| jq 命令语法正确 | ✅ | 使用 `jq` 的 `.field = value` 写法的语法正确（但有个问题见下方） |
| 保留已有配置 | ✅ | `jq` 输出完整 JSON，只修改指定字段，不覆盖其他 |
| 嵌套字段修改正确 | ⚠️ | `fix_config_field` 函数用了 `cat` 整个文件→临时文件→`cp` 覆盖，原子性OK |

**问题 1**：`fix_config_field` 函数多处只传一个参数但函数签名看起来对上了：

```bash
fix_config_field '.gateway.port = 16878' 'gateway.port = 16878'
# 第一个参数是 jq_filter，第二个参数是 desc
```

定义是 `$1=jq_filter, $2=desc`，调用匹配，没问题。⚠️ 降为观察项。

**问题 2**：`fix_config_field` 函数内部的 `mktemp` 写法。在脚本开头没有设置 `trap` 清理临时文件（不过函数内已 `rm -f`）。如果 `jq` 执行中途脚本被 kill，临时文件会残留。风险较低。

**改进建议**：建议给脚本增加 trap：
```bash
TEMP_FILES=()
cleanup() {
    for f in "${TEMP_FILES[@]}"; do rm -f "$f"; done
}
trap cleanup EXIT
```

---

### 3. 目录创建安全性 — ✅

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 路径正确 | ✅ | `${OCC_WORKSPACE}/memory` 和 `${OCC_WORKSPACE}/skills` |
| 权限设置合理 | ✅ | `chown -R "${OCC_USER}:${OCC_USER}"` |
| 正确的用户 | ✅ | `sudo_exec` 使用 `sudo -S -u "${OCC_USER}"` |
| 有验证 | ✅ | 创建后检查目录是否存在 |

无问题。

---

### 4. 服务启动安全性 — ⚠️

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 使用正确 Node v24 路径 | ✅ | `${NODE_V24_PATH}` 硬编码，前有检查 |
| 检查端口占用 | ✅ | `ss -tlnp` 检查端口 |
| 杀掉旧进程再启动 | ✅ | Gateway 部分有 pkill + sleep + 强杀逻辑 |
| 使用 nohup 后台运行 | ✅ | `nohup ... > log 2>&1 &` |
| 正确的用户 | ✅ | 首选 `sudo -u "${OCC_USER}"`，有 fallback |

**问题 1**：`pkill -f "openclaw gateway"` 过于宽泛。如果有其他进程的命令行包含 "openclaw gateway" 子串，会被误杀。风险中等。

**改进建议**：
```bash
# 更精确的进程匹配
OLD_GATEWAY_PID=$(pgrep -f "node.*openclaw.*gateway" 2>/dev/null || true)
```

**问题 2**：sleep 2 / sleep 1 的等待是硬编码。建议改进为等待循环（retry loop）。

**问题 3**：编辑器启动使用了 `sudo -S -u` 和 fallback（不用 sudo），这两个路径可能行为不一致。二次调用时如果第一次 sudo 失败但没退出就 fallback 了，编辑器可能以 root 权限运行。

---

### 5. 错误处理完整性 — B

| 检查项 | 结果 | 说明 |
|--------|------|------|
| `set -euo pipefail` | ✅ | 脚本第9行 |
| 每个关键步骤有错误检测 | ✅ | Node 存在性检查、jq 存在性检查、端口占用检查 |
| 回滚机制 | ❌ | **无回滚机制**。步骤 1 删了旧 node 后，步骤 2 如果失败，脚本会 exit，系统处于 node 文件和配置修改一半的不一致状态 |
| 最终验证 | ✅ | 步骤 5 验证了 node 版本、端口监听、配置、目录 |

**改进建议**：
```bash
ROLLBACK_NEEDED=false

rollback() {
    if [ "${ROLLBACK_NEEDED}" = true ]; then
        warn "执行回滚..."
        # 恢复 node 软链接
        if [ -f "/usr/bin/node.v18.bak" ]; then
            sudo_exec "恢复 Node v18" mv /usr/bin/node.v18.bak /usr/bin/node
        fi
        # 恢复配置
        if [ -f "${CONFIG_BACKUP}" ] && [ -f "${OCC_CONFIG}" ]; then
            warn "恢复配置备份: ${CONFIG_BACKUP}"
            cp "${CONFIG_BACKUP}" "${OCC_CONFIG}"
        fi
        ok "回滚完成"
    fi
}
trap rollback EXIT
```

然后在步骤 1 删除 node 前设置 `ROLLBACK_NEEDED=true`，步骤 5 验证通过后设置 `ROLLBACK_NEEDED=false`。

---

### 6. 潜在风险点 — 🔴 严重

| 检查项 | 结果 | 严重程度 | 说明 |
|--------|------|----------|------|
| sudo 密码硬编码 | 🔴 | **严重** | `SUDO_PASSWORD="xiaoxiao1983620"` 明文硬编码在第23行。任何能读文件的用户/进程都能拿到 sudo 密码 |
| 密码通过 `echo` 管道传递 | 🔴 | **严重** | `echo "${SUDO_PASSWORD}" | sudo -S` 会让密码出现在 bash 的进程列表中（`ps aux` 可见），而且 shell history 可能记录 |
| 硬编码敏感信息 | 🔴 | **中等** | 服务器地址 `qh.tdx1146.com`、用户名 `tdx1146` 明文化 |

**解决方案**（优先级最高）：
1. **删除硬编码密码**。改用 `sudo -K` 先验证缓存（如果最近 sudo 过），或要求用户在脚本开始时手动输入一次
2. 或者使用 `SUDO_ASKPASS` 脚本 + `sudo -A` 而不是 `echo | sudo -S`

**具体改进建议**：
```bash
# 方式 A：问一次密码
read -rsp "请输入 sudo 密码: " SUDO_PASSWORD
echo ""

# 方式 B（更安全）：不存变量，每次 sudo 前 askpass
SUDO_ASKPASS=/tmp/sudo_askpass.sh
cat > "${SUDO_ASKPASS}" << 'ASKPASS_EOF'
#!/bin/sh
echo "${SUDO_PASSWORD}"
ASKPASS_EOF
chmod +x "${SUDO_ASKPASS}"

# 使用时
SUDO_ASKPASS="${SUDO_ASKPASS}" sudo -A rm -f "${node_path}"
```

**不论采用哪种方式，每次调用 `sudo` 时密码不应该出现在命令行参数或 `ps` 可见的位置。**

3. 服务器地址和用户名使用环境变量或 `.env` 文件，不硬编码。

---

## 其他发现

### 风格/可靠性问题

| 问题 | 位置 | 说明 |
|------|------|------|
| `while read -r line` 无 `IFS=` | 第 231 行附近 | `ss` 输出包含空格，最好用 `while IFS= read -r line` |
| `sudo_exec` 函数内 `2>&1` 用 `sudo` | 多处 | 标准做法，但 `sudo -S "$@"` 把参数直接解析，如果参数包含空格会出问题 |
| `cd` 无错误处理 | `cd "${EDITOR_DIR}"` | 如果目录存在但无法 cd（权限问题），脚本不会退出 |
| 无日志文件 | 整个脚本 | 没有自己的日志文件，所有输出到 stdout，ssh 会话断开后输出丢失 |

### 改进建议汇总

按优先级排序：

1. **🔴 必须修**：移除硬编码 sudo 密码
2. **🔴 必须修**：改用 `SUDO_ASKPASS` 或交互式输入，避免密码出现在 `ps` 列表
3. **🟡 建议修**：增加回滚机制（rollback trap）
4. **🟡 建议修**：增加脚本自身日志文件（`${SCRIPT_LOG}`）
5. **🟢 可选的**：删除 node 前备份原始路径
6. **🟢 可选的**：精确化 `pkill` 匹配模式
7. **🟢 可选的**：`while read -r` 前加 `IFS=`
8. **🟢 可选的**：增加 `trap` 清理临时文件

---

## 结论

该脚本在**功能层面**设计合理 — 结构清晰、步骤完整、验证充分。但**安全层面存在严重漏洞**（密码硬编码+明文传递），在部署到任何非隔离环境前必须修复。评级从 C 降至 D 挂起，修复后可达 B 级。

| 状态 | 要求 |
|------|------|
| 🔴 阻塞 | 密码硬编码问题未修复前，**切勿**将此脚本提交到 git 仓库或传输给其他人 |
| 🟡 注意 | 如远程执行，日志输出到终端的部署详情（含服务器信息）可能被记录 |
| ✅ 可运行 | 在受控环境（无其他用户、私密 SSH 会话）中可以执行，但风险自担 |
