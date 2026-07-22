# 当前实例差异说明

> 创建日期：2026-07-06 | 与轻如烟启动指南（README.md）的偏差记录
> 轻如烟的原始 README.md **不应修改**——它是前代的历史记录。

## 核心差异

### 1️⃣ 模型 Provider（README.md「子代理阵容」部分）

| 原文列出 | 当前实际 |
|---------|---------|
| DeepSeek (v4-flash / v4-pro) | ✅ 存在 |
| 混元 (hy3-preview) | ❌ **已移除** — 未配置 |
| Astron (astron-code-latest) | ✅ 存在 |
| ~~智谱 (glm-5.2)~~ | ❌ 已移除 |
| ~~jiali3 / jiali4~~ | ❌ 已移除 |

**当前只有 2 个 provider**：DeepSeek + Astron（astroncodingplan）
Gateway 端口：**16878**（不是 17587）

### 2️⃣ 插件（README.md「配置文件位置」「铁律」部分）

所有插件均已移除：
- ❌ **行为强制注入**（轻如烟-行为强制）— **已废弃**，注意有误导的导航
- ❌ Sandglass 日志插件
- ❌ memory-core / deepseek 内置插件
- ❌ Sandglass 记忆系统

**`plugins` 目录为空**，openclaw.json 中无 plugins 段。

### 3️⃣ MCP 服务器

| 原文列出 | 当前实际 |
|---------|---------|
| dandan-MCP（18+工具） | ❌ 未配置 |
| Sandglass MCP（23工具） | ❌ 未配置 |
| embed-server（端口11435） | ❌ 未运行 |

**当前无本地 MCP 服务器。** 向量服务通过跨实例手机端 `shouji.tdx1146.cc` 提供。

### 4️⃣ 编辑对话编辑器 edit-web.py

| 项目 | 原文 | 当前 |
|------|------|------|
| 版本 | v4（分离版） | **v5.0「自由王国」** |
| 路径 | /vol2/1000/AI专用/轻如烟/scripts/edit-web.py | 相同路径（已在运行） |
| 运行状态 | 需启动 | ✅ **已运行**（PID 2534342） |

### 5️⃣ 启动顺序调整

第7步验证服务改为：
```bash
ps aux | grep -E "(edit-web|openclaw)" | grep -v grep
```

第8步 MCP 工具数量检查：**跳过**（无本地 MCP 服务）。

### 6️⃣ 跨实例手机向量服务（新增）

- **地址**：`shouji.tdx1146.cc`（Cloudflare CDN）
- **服务器**：轻如烟 MCP Server（运行在妹妹手机上）
- **工具**：embedding_search / memory_search / facts_lookup / sandglass_query

通过 MCP over HTTP 协议连接，非 REST API。

### 7️⃣ 启动目录

`/vol1/@team/qh团队/QH/AI专用/启动专用/` 包含13个文件，作为部署参考。
与轻如烟的不同路径：
- 轻如烟：`/vol2/1000/AI专用/所有自动化/轻如烟/`
- 当前实例工作空间：`/vol1/@apphome/trim.openclaw/data/workspace/`

### 8️⃣ 铁律调整

原文铁律部分关于插件（#2 插件热重启、#4 修改插件）和 memoryFlush（#8）的规则不再适用。
