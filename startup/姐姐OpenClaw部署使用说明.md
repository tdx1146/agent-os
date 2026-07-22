# 🌫️ 姐姐 OpenClaw 一键部署方案 — 使用说明

> **版本**：v1.0
> **日期**：2026-07-08
> **目标**：让姐姐在重装 OpenClaw 后快速恢复完整环境

---

## 一、方案概述

### 适用场景

- ✅ 姐姐服务器刚重装 OpenClaw
- ✅ Gateway 端口被覆盖（44376 → 16878）
- ✅ session 配置丢失（scope/dmScope 为 null）
- ✅ Node.js 版本错误（v18 而非 v24）
- ✅ 编辑器未启动
- ✅ workspace/memory 目录缺失

### 解决的问题

| 问题 | 解决方式 | 预计时间 |
|------|---------|---------|
| Node v18 残留 | 删除 + 创建 v24 软链接 | 30秒 |
| Gateway 端口错误 | jq 修复配置 | 10秒 |
| session 配置缺失 | jq 修复配置 | 10秒 |
| auth.mode 未声明 | jq 修复配置 | 10秒 |
| 目录缺失 | mkdir 创建 | 5秒 |
| 编辑器未运行 | nohup 启动 | 5秒 |
| Gateway 未运行 | 重启服务 | 10秒 |
| **总计** | **一键执行** | **~2分钟** |

---

## 二、使用步骤

### Step 1：SSH 登录姐姐服务器

```bash
ssh tdx1146@qh.tdx1146.com
# 密码：xiaoxiao1983620
```

### Step 2：进入启动专用目录

```bash
cd /vol1/@team/qh团队/QH/AI专用/启动专用/
```

### Step 3：运行部署脚本

```bash
bash deploy_openclaw_qh.sh
```

### Step 4：等待执行完成

脚本会自动执行以下步骤：

```
步骤 1/5 — 删除 Node v18，安装 Node v24
步骤 2/5 — 修复 OpenClaw 配置
步骤 3/5 — 创建目录结构
步骤 4/5 — 启动服务
步骤 5/5 — 验证部署结果
```

### Step 5：查看验证结果

脚本最后会输出验证结果：

```
══════ 验证结果 ══════
1. Node 版本: v24.15.0 ✅
2. Gateway 健康检查: {"ok":true,"status":"live"} ✅
3. 编辑器检查: HTTP 200 ✅
4. 配置验证: 全部正确 ✅
5. 目录检查: 全部就绪 ✅
6. 端口监听: 16878, 18888 ✅

✅ 全部服务运行正常！
```

---

## 三、文件清单

### 已传输到姐姐服务器的文件

| 文件名 | 大小 | 用途 |
|--------|------|------|
| `deploy_openclaw_qh.sh` | 17KB | 一键部署脚本 |
| `deploy_audit_report.md` | 8.5KB | 环境审计报告 |
| `OpenClaw配置踩坑汇总-启动必读.md` | 16KB | 配置踩坑清单 |
| `统一搜索程序-v1.0.md` | 6KB | 搜索方法论 |

**位置**：`/vol1/@team/qh团队/QH/AI专用/启动专用/`

---

## 四、脚本功能详解

### 1. 删除 Node v18，安装 Node v24

**原因**：姐姐服务器上 Node v18 和 v24 共存，OpenClaw 可能用错版本。

**操作**：
- 删除 `/usr/bin/node`（v18 软链接）
- 创建 `/usr/bin/node` → `/var/apps/nodejs_v24/target/bin/node`（v24）
- 创建 `/usr/bin/npm` → `/var/apps/nodejs_v24/target/bin/npm`
- 验证版本：`node --version` 应输出 `v24.15.0`

**风险**：低。删除前会检查文件是否存在，不会误删。

---

### 2. 修复 OpenClaw 配置

**修复项**：
| 配置项 | 当前值 | 正确值 |
|--------|--------|--------|
| `gateway.port` | 44376 | 16878 |
| `session.scope` | null | "global" |
| `session.dmScope` | null | "main" |
| `gateway.auth.mode` | 缺失 | "token" |
| `models.providers.astron2.contextTokens` | null | 256000 |
| `models.providers.deepseek.contextTokens` | 1000000 | 1000000（保留） |

**备份**：修改前会自动备份到 `openclaw.json.bak.时间戳`

**风险**：低。有备份，可回滚。

---

### 3. 创建目录结构

**创建目录**：
- `/vol1/@apphome/trim.openclaw/data/workspace/memory/`
- `/vol1/@apphome/trim.openclaw/data/workspace/skills/`

**权限**：`trim.openclaw:trim.openclaw`

**风险**：极低。仅创建目录。

---

### 4. 启动服务

**启动编辑器**：
- 路径：`/vol1/@team/qh团队/QH/AI专用/编辑器所有版本/v5.0_20260701_freedom/`
- 端口：18888
- 日志：`/tmp/edit-web.log`

**启动 Gateway**：
- 使用 Node v24
- 端口：16878
- 日志：`/tmp/gateway.log`
- 启动前会杀掉旧进程

**风险**：中。会杀掉旧的 Gateway 进程，当前对话会中断。

---

### 5. 验证结果

**验证项**：
1. Node 版本：v24.15.0
2. Gateway 健康检查：`http://127.0.0.1:16878/health`
3. 编辑器响应：`http://127.0.0.1:18888/`
4. 配置正确性：jq 提取关键字段验证
5. 目录存在性：ls 检查
6. 端口监听：ss 检查

---

## 五、常见问题

### Q1: 脚本执行失败怎么办？

**检查日志**：
```bash
# Gateway 日志
tail -50 /tmp/gateway.log

# 编辑器日志
tail -50 /tmp/edit-web.log
```

**手动启动**：
```bash
# 启动编辑器
cd /vol1/@team/qh团队/QH/AI专用/编辑器所有版本/v5.0_20260701_freedom/
nohup python3 edit-web.py > /tmp/edit-web.log 2>&1 &

# 启动 Gateway
export PATH="/var/apps/nodejs_v24/target/bin:$PATH"
nohup node /vol1/@apphome/trim.openclaw/data/openclaw/node_modules/.bin/openclaw gateway > /tmp/gateway.log 2>&1 &
```

---

### Q2: Node 版本仍然是 v18？

**手动修复**：
```bash
sudo rm /usr/bin/node
sudo ln -s /var/apps/nodejs_v24/target/bin/node /usr/bin/node
node --version  # 应输出 v24.15.0
```

---

### Q3: Gateway 端口仍然是 44376？

**手动修复**：
```bash
# 检查配置
jq '.gateway.port' ~/.openclaw/openclaw.json

# 修复
jq '.gateway.port = 16878' ~/.openclaw/openclaw.json > /tmp/oc.json
sudo mv /tmp/oc.json ~/.openclaw/openclaw.json

# 重启 Gateway
sudo pkill -f "openclaw gateway"
export PATH="/var/apps/nodejs_v24/target/bin:$PATH"
nohup node /vol1/@apphome/trim.openclaw/data/openclaw/node_modules/.bin/openclaw gateway > /tmp/gateway.log 2>&1 &
```

---

### Q4: 编辑器无法访问？

**检查**：
```bash
# 检查进程
ps aux | grep edit-web

# 检查端口
ss -tlnp | grep 18888

# 检查日志
tail -50 /tmp/edit-web.log

# 测试访问
curl http://127.0.0.1:18888/
```

---

### Q5: 如何回滚配置？

```bash
# 查看备份文件
ls -la ~/.openclaw/openclaw.json.bak.*

# 恢复备份
cp ~/.openclaw/openclaw.json.bak.XXXXXX ~/.openclaw/openclaw.json

# 重启 Gateway
sudo pkill -f "openclaw gateway"
# ... 手动启动
```

---

## 六、安全说明

### 高风险操作

| 操作 | 风险 | 缓解措施 |
|------|------|---------|
| 删除 Node v18 | 中 | 先检查文件类型，不误删 |
| 修改 openclaw.json | 中 | 自动备份，可回滚 |
| 重启 Gateway | 高 | 当前对话中断，需确认无活跃对话 |
| 杀掉旧进程 | 高 | 可能影响正在运行的服务 |

### 安全措施

- ✅ 修改前自动备份
- ✅ 每步都有验证
- ✅ 错误立即停止（`set -euo pipefail`）
- ✅ sudo 操作需密码确认
- ✅ 最终输出验证结果

---

## 七、后续维护

### 每次重装后必做

1. 运行部署脚本
2. 验证所有服务正常
3. 测试编辑器访问
4. 测试 Gateway 健康检查

### 定期检查

```bash
# 一键检查脚本
bash /vol1/@team/qh团队/QH/AI专用/启动专用/check_openclaw_qh.sh 2>/dev/null || echo "检查脚本不存在，需创建"
```

---

## 八、联系支持

**问题反馈**：轻如烟（轻如烟编辑器对话）

**参考文档**：
- `OpenClaw配置踩坑汇总-启动必读.md` — 配置问题速查
- `统一搜索程序-v1.0.md` — 搜索方法论
- `deploy_audit_report.md` — 环境审计报告

---

_版本：v1.0_
_创建时间：2026-07-08 16:22_
_下次更新：根据审计结果优化_