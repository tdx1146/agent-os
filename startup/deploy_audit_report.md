# 审计报告：姐姐 OpenClaw 部署环境

> 审计时间：2026-07-08 16:02
> 审计范围：当前运行环境 + openclaw.json 配置
> 注意：独立部署脚本文件 (`deploy_openclaw_qh.sh`) **未找到**。审计基于实际运行状态及 openclaw.json 的当前内容（对照备份 `openclaw.json.bak` 的差异）。

---

## 审计结果

### 1. Node.js 版本

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 当前 Node 版本 | ✅ `v24.15.0` | 符合预期，新版本 |
| Node 路径 | ✅ `/vol1/@appcenter/nodejs_v24/bin/node` | 标准 container 路径 |
| npm 版本 | ✅ `11.12.1` | 与 Node v24 匹配 |
| `/usr/bin/node` | ✅ 不存在 | v18 已非系统链接，干净 |
| `/usr/local/bin/node` | ✅ 不存在 | 无残留 |

**结论**: ✅ Node 版本正常，无 v18 残留。

---

### 2. 配置修改安全性

#### 2.1 备份情况

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 存在备份文件 | ✅ | `openclaw.json.bak` (8030 bytes, 修改于 2026-06-23 20:51) |
| 备份权限 | ✅ | `-rw-------` (仅 owner 可读写) |
| 备份完整性 | ✅ | 可比较 diff，结构完整 |

#### 2.2 关键配置差异分析

对照 `openclaw.json`（当前）与 `openclaw.json.bak`（备份），主要变化：

**新增模型提供方：**
| 项目 | 状态 | 评估 |
|------|------|------|
| `jiali3` 提供方 (deepseek-v4-flash/pro) | ✅ 存在 | API key: `sk-655b...` |
| `jiali4` 提供方 (deepseek-v4-flash/pro) | ✅ 存在 | API key: `sk-d91a...` |
| `jiali3` 模型缺少 `contextWindow` | ⚠️ | 未设置 contextWindow，默认值可能不准确 |
| `jiali4` 模型缺少 `contextWindow` | ⚠️ | 同上 |
| `jiali3/jiali4` 模型缺少 `input:["image"]` | ⚠️ | 仅支持 `["text"]`，限制了多模态能力 |
| `google` 模型缺少 `input:["image"]` | ⚠️ | 备份中有 `"image"` 但当前版本没有 |

**defaults 配置：**
| 项目 | 状态 | 评估 |
|------|------|------|
| `contextTokens`: 200000 | ✅ 存在 | 备份中原本在 `智谱` 提供方内，现在提升到 defaults 层 |
| `memorySearch.enabled`: false | ✅ | 已禁用，符合架构原则（主力用沙漏） |
| `imageModel`: 智谱/glm-5.2 | ✅ | 正确配置 |

**agents 配置：**
| 项目 | 状态 | 评估 |
|------|------|------|
| main agent 使用 `astron2/astron-code-latest` | ✅ | 配置正确 |
| main agent fallbacks 含 deepseek/混元 | ✅ | 合理的降级链 |
| deepseek 子代理用 `jiali3/deepseek-v4-flash` | ✅ | 配置正确 |
| deepseek 子代理 fallbacks 含 jiali4/deepseek | ✅ | 合理的降级链 |
| main agent subagents 限制为 `"*"` | ⚠️ | 未限制子代理模型，可能调用非预期模型 |

**session 配置：**
| 项目 | 状态 | 评估 |
|------|------|------|
| `scope: "per-sender"` | ✅ 当前 | 备份中是 `"global"`，当前修改更安全 |
| `scope` 改成 per-sender | ✅ | 防止跨 session 污染，正确的修改 |
| `sessionIdleTtlMs`: 300000 (5min) | ❓ 当前 | 备份中是 30000 (30s)，改成了 5min，需要确认意图 |

**cron compaction：**
| 项目 | 状态 | 评估 |
|------|------|------|
| `every: "0m"` | ❌ | **备份中是 "6h"**，当前设为 "0m" 表示 compaction 可能永远不会触发 |
| `memoryFlush.enabled: false` | ✅ | 合理（沙漏主力） |

**plugin 变更：**
| 项目 | 状态 | 评估 |
|------|------|------|
| 移除了 `sandglass-logger` | ✅ | 合理（沙漏已整合） |
| 移除了轻如烟-行为强制 | ✅ | 合理（已整合到系统） |
| plugins 列表干净 | ✅ | 只保留必要插件 |

**tools.embed：**
| 项目 | 状态 | 评估 |
|------|------|------|
| embed 配置缺失 | ⚠️ | 备份中有 embed 配置（bge-m3 模型），当前版本没有 |

**其他：**
| 项目 | 状态 | 评估 |
|------|------|------|
| `update.checkOnStart: false` | ✅ | 合理，生产环境不应自动检查更新 |
| `ownerAllowFrom: ["webchat"]` 已移除 | ✅ | 减少了攻击面 |
| `ownerDisplay: "raw"` 保留 | ✅ | 保持简洁 |
| `auth.token` 存在 | ✅ | 认证配置完整 |
| Astron API key 使用环境变量 `$ASTRON_API_KEY` | ✅ | 安全做法 |
| jiali3/jiali4 API key 明文硬编码 | ❌ | 存在泄露风险 |

---

### 3. 目录和权限

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 身份文件权限 | ✅ | 正常 |
| openclaw.json 权限 | ✅ | `-rw-r--r--` (644) |
| openclaw.json.bak 权限 | ✅ | `-rw-------` (600) |
| 节点路径是否存在 | ✅ | `/vol1/@appcenter/nodejs_v24/bin/node` |

---

### 4. 服务运行状态

| 检查项 | 结果 | 说明 |
|--------|------|------|
| openclaw 进程运行中 | ✅ | PID 246975，启动于 Jul06 |
| systemd 单元 | ✅ | 存在但处于 inactive 状态 (PID=0) |
| openclaw 用户 | ✅ | `trim.openclaw` 运行 |
| 端口 17587 | ✅ | 配置为 loopback 绑定 |
| 其他相关进程 | ✅ | Hermes, bun server, proxy, MCP server 均运行中 |
| Nanobot gateway | ✅ | 运行中 |

---

### 5. 错误处理和验证

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 备份存在 | ✅ | `.bak` 文件完整 |
| 无回滚脚本 | ⚠️ | 没有独立的回滚脚本 |
| 无部署脚本 | ❌ | `deploy_openclaw_qh.sh` 不存在，无法审计 |

---

## 问题总结

### ❌ 关键问题

1. **cron compaction 频率设为 `"0m"`**
   - 备份中是 `"6h"`，当前设为 `"0m"` 可能导致 memory compaction 永远不触发
   - 需要确认是否是有意禁用

2. **API key 明文硬编码**
   - `jiali3` 和 `jiali4` 的 DeepSeek API key 直接在 openclaw.json 中明文存储
   - 建议使用环境变量引用（如 Astron 已做的 `$ASTRON_API_KEY`）

### ⚠️ 中等问题

1. **部署脚本缺失**
   - 独立部署脚本文件 `deploy_openclaw_qh.sh` 不存在
   - 无法审计脚本的安全性
   - 建议创建标准部署脚本，包含完整错误处理和验证

2. **`jiali3` / `jiali4` 模型配置不完整**
   - 缺少 `contextWindow` 字段（备份中有 contextWindow 设置，当前版本没有）
   - jiali3/jiali4 的 deepseek-v4 模型应该设置 `contextWindow: 1000000`（与 DeepSeek 官方一致）

3. **`google` 模型缺少 `input:["image"]`**
   - 备份中 google 模型支持 image 输入，当前版本丢失了
   - 这限制了对 Gemini 模型的图片处理能力

4. **`tools.embed` 配置缺失**
   - 备份中有 embed server 配置（bge-m3，192.168.0.103:11435），当前没有
   - 即使 memorySearch 已禁用，embed 配置可能是其他工具需要的

5. **无回滚机制**
   - 如果配置修改导致问题，没有自动回滚脚本
   - 只能手动用 `.bak` 文件恢复

### 🟢 改进建议

1. **创建标准部署脚本** (`deploy_openclaw.sh`)
   ```bash
   #!/bin/bash
   set -euo pipefail

   # 1. 备份
   cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.$(date +%Y%m%d_%H%M%S)

   # 2. 验证 Node 版本
   NODE_PATH="/vol1/@appcenter/nodejs_v24/bin/node"
   if ! $NODE_PATH --version | grep -q "v24"; then
     echo "ERROR: Node v24 不可用"
     exit 1
   fi

   # 3. 验证 JSON 语法
   jq . ~/.openclaw/openclaw.json > /dev/null || { echo "JSON 语法错误"; exit 1; }

   # 4. 验证模型配置完整性
   MODEL_COUNT=$(jq '.models.providers | length' ~/.openclaw/openclaw.json)
   echo "模型提供方: $MODEL_COUNT"

   # 5. 重启
   # systemctl --user restart openclaw-gateway
   ```

2. **API key 迁移到环境变量**
   ```json
   "jiali3": {
     "apiKey": "${JIALI3_API_KEY}"
   }
   ```

3. **补全 jiali3/jiali4 模型 contextWindow**
   ```json
   {
     "id": "deepseek-v4-flash",
     "contextWindow": 1000000,
     "input": ["text"]
   }
   ```

4. **恢复 google 模型的 image 输入**
   ```json
   "models": [{
     "input": ["text", "image"]
   }]
   ```

5. **恢复 compaction 频率或明确禁用**
   - 如果禁用 compaction，添加注释说明原因
   - 如果需要 compaction，设回 `"6h"`

---

## 总体评分

| 维度 | 评分 | 说明 |
|------|------|------|
| Node 版本管理 | ✅ 优秀 | 干净无残留 |
| 配置完整性 | ⚠️ 一般 | contextWindow 缺失、cron 频率异常 |
| 安全管理 | ⚠️ 一般 | API key 明文，无部署脚本 |
| 运行时健康 | ✅ 优秀 | 所有服务正常运行 |
| 备份机制 | ✅ 良好 | 有备份但无自动回滚 |

**总体评级：B（良好，但有几项需要注意）**

**优先级建议：**
1. 🔴 恢复 compaction 频率或明确注释
2. 🔴 补全 jiali3/jiali4 model contextWindow
3. 🟡 API key 迁移到环境变量
4. 🟡 修复 google 模型 image 支持
5. 🟢 创建标准部署脚本 + 回滚脚本
