# OpenClaw 配置审计报告

> 审计日期：2026-07-01
> OpenClaw 版本：2026.6.9 (已安装，缓存中有 2026.6.11)
> 审计范围：config → workspace → plugins → agents → hooks → MCP
> 审计方法：对照官方文档逐字段验证

---

## 一、配置概览

**配置文件位置**: `~/.openclaw/openclaw.json`
**实际路径**: `/vol1/@apphome/trim.openclaw/data/home/.openclaw/openclaw.json`

### 元数据

| 字段 | 值 | 官方要求 |
|------|-----|---------|
| `meta.lastTouchedVersion` | `2026.6.9` | 无约束 |
| `update.checkOnStart` | `false` | 可选优化项，合理 |

---

## 二、models.providers 检查

### 2.1 已配置的 Provider 列表

| Provider | API 类型 | API Key 来源 | API Key 安全性 | 问题 |
|----------|----------|-------------|---------------|------|
| 混元 | `openai-completions` | 环境变量 `${HUNYUAN_API_KEY}` | ✅ 安全（环境变量引用） | — |
| 智谱 | `openai-completions` | 环境变量 `${ZHIPU_API_KEY}` | ✅ 安全 | — |
| deepseek | `openai-completions` | 明文硬编码 | ⚠️ **不安全** | API Key 直接内联在配置文件中 |
| jiali3 | `openai-completions` | 明文硬编码 | ⚠️ **不安全** | API Key 直接内联 |
| jiali4 | `openai-completions` | 明文硬编码 | ⚠️ **不安全** | API Key 直接内联 |
| astron2 | `openai-completions` | 明文硬编码 | ⚠️ **不安全** | API Key + Secret 组合直接内联 |

### 2.2 问题：API Key 明文硬编码

**严重性**: 🔴 高
**说明**: deepseek、jiali3、jiali4、astron2 的 API Key 直接以明文写入 `openclaw.json`。官方文档明确推荐使用 `${VAR_NAME}` 环境变量引用方式。

**修复建议**:
```json5
// 正确做法
"deepseek": {
  "api": "openai-completions",
  "baseUrl": "https://api.deepseek.com",
  "apiKey": "${DEEPSEEK_API_KEY}"  // 环境变量引用
}
```

同时在 `.env` 或系统环境中设置：
```
DEEPSEEK_API_KEY=sk-xxxx...
JIALI3_API_KEY=sk-xxxx...
JIALI4_API_KEY=sk-xxxx...
ASTRON_API_KEY=xxxx...
```

### 2.3 问题：混元 API 端点可能过时

**严重性**: 🟡 中
**说明**: 当前使用的混元端点 `https://api.lkeap.cloud.tencent.com/plan/v3` 与 deepseek agent 的 `models.json` 中混元端点 `https://api.hunyuan.cloud.tencent.com/v1` 不一致。

**修复建议**: 确认哪个端点是当前有效的。从文档来看，`plan/v3` 路径可能是一个特定子路径。如果是统一 API，建议只用统一端点并在配置中统一。

### 2.4 没有问题：astron2 的 apiKey 同时包含 secret

实际上在 `openai-completions` 模式中，`apiKey` 字段通常只接受 API Key。astron2 配置中 `apiKey: "key:secret"` 格式可能是该服务商的要求。**这不是配置错误**，但建议确认文档。

---

## 三、agents.list 检查

### 3.1 代理定义完整性

| Agent ID | 模型主选 | Fallbacks | Workspace | Subagent 配置 | 问题 |
|----------|---------|-----------|-----------|--------------|------|
| `main` | `astron2/astron-code-latest` | deepseek-v4-flash, hy3-preview | ✅ 指定 | ✅ allowAgents: "*" | — |
| `deepseek` | `jiali3/deepseek-v4-flash` | jiali4, deepseek | ✅ 指定 | 未明确设置 | — |

### 3.2 问题：`main` agent 的主模型 astron2 未验证

**严重性**: 🟡 中
**说明**: `astron2/astron-code-latest` 配置在 `models.providers.astron2` 中，但其 API Key 是硬编码且其格式可能与其他 provider 不同。

### 3.3 问题：agent `main` 缺少 `name` 字段

**严重性**: 🟢 低
**说明**: `agents.list` 中的条目建议设置 `name` 字段（文档中鼓励但不强制）。另一个 agent `deepseek` 已设置 `name: "DeepSeek 子代理"`。

**修复建议**:
```json5
{
  "id": "main",
  "name": "主代理",
  // ... 其余字段不变
}
```

### 3.4 问题：agent `main` 允许所有子代理但 agent `deepseek` 未声明 subagents

**严重性**: 🟢 低
**说明**: `main` 设置了 `subagents.allowAgents: ["*"]`，这是合理的。`deepseek` agent 未设置 `subagents` 字段，将继承默认行为（仅允许自身），这与预期一致。

### 3.5 注意：agent `deepseek` 没有 `models` 字段

**说明**: `deepseek` agent 没有在 `agents.list[].models` 中指定模型 override，因此完全继承 `agents.defaults.models`。这不会导致功能问题。

---

## 四、compaction 配置检查

### 4.1 当前配置

```json5
"compaction": {
  "memoryFlush": {
    "enabled": true,
    "softThresholdTokens": 4000,
    "prompt": "...",
    "systemPrompt": "..."
  },
  "postCompactionSections": ["启动", "铁律"]
}
```

### 4.2 评估

| 字段 | 当前值 | 官方默认 | 问题 |
|------|--------|---------|------|
| `mode` | 未设置 → `safeguard` | `safeguard` | ✅ 正确 |
| `memoryFlush.enabled` | `true` | `true` | ✅ 正确 |
| `memoryFlush.softThresholdTokens` | `4000` | `6000` | 🟡 低于默认值，但合法 |
| `postCompactionSections` | `["启动", "铁律"]` | 未设置（=禁用） | ✅ 合理自定义 |
| `keepRecentTokens` | 未设置 | `50000` | ✅ 使用默认值 |
| `notifyUser` | 未设置 | `false` | ✅ 使用默认值 |
| `truncateAfterCompaction` | 未设置 | `false` | 🟡 未开启转录裁剪 |
| `model` | 未设置 | 使用 session 主模型 | ✅ 使用默认值 |

### 4.3 问题：无 compaction model 专用

**严重性**: 🟢 低
**说明**: 当前未设置 `compaction.model`，压缩使用 session 主模型。如果希望将压缩任务从主模型分离出来，可以设置一个轻量模型。

### 4.4 问题：未设置 truncateAfterCompaction

**严重性**: 🟢 低
**说明**: `truncateAfterCompaction` 未设为 `true`，意味着压缩后转录文件不会裁剪。长时间运行后 session JSONL 文件会持续增长。

**修复建议**（可选）:
```json5
"compaction": {
  "truncateAfterCompaction": true,
  // 其余字段保持不变
}
```

---

## 五、memorySearch 配置检查

### 5.1 当前配置

```json5
"memorySearch": {
  "enabled": true
}
```

### 5.2 评估

| 字段 | 当前值 | 官方默认 | 问题 |
|------|--------|---------|------|
| `enabled` | `true` | `true` | ✅ 正确 |
| `provider` | 未设置 | `"openai"` | 🟢 使用默认 OpenAI |
| `query.hybrid.enabled` | 未设置 | `true` | ✅ 使用默认（混合搜索） |
| `query.hybrid.mmr` | 未设置 | `disabled` | 🟢 使用默认 |
| `query.hybrid.temporalDecay` | 未设置 | `disabled` | 🟢 使用默认 |

### 5.3 建议启用 MMR 和 Temporal Decay

**严重性**: 🟢 建议
**说明**: 当前系统运行数月（从日志看自 2026-05），daily memory 文件可能较多。建议开启 MMR（去重）和 Temporal Decay（时间衰减）以提升搜索质量。

**修复建议**:
```json5
"memorySearch": {
  "enabled": true,
  "query": {
    "hybrid": {
      "mmr": { "enabled": true },
      "temporalDecay": { "enabled": true }
    }
  }
}
```

---

## 六、plugins 配置检查

### 6.1 当前配置

```json5
"plugins": {
  "enabled": true,
  "allow": ["轻如烟-行为强制", "deepseek", "memory-core", "sandglass-logger"],
  "load": {
    "paths": ["/vol1/.../plugins/轻如烟-行为强制", "/vol1/.../plugins/sandglass-logger"]
  },
  "entries": {
    "轻如烟-行为强制": { "enabled": true, "hooks": { "allowPromptInjection": true } },
    "deepseek": { "enabled": true },
    "memory-core": { "enabled": true, "config": { "dreaming": { "enabled": true } } }
  },
  "bundledDiscovery": "compat"
}
```

### 6.2 评估

| 插件 | `allow` 列表 | `load.paths` | `entries` | 问题 |
|------|------------|-------------|-----------|------|
| 轻如烟-行为强制 | ✅ | ✅ | ✅ | — |
| deepseek | ✅ | ❌ 未配置加载路径 | ✅ | 🟡 可能是内置/内置插件 |
| memory-core | ✅ | ❌ 未配置加载路径 | ✅ | 🟡 内置插件，正常 |
| sandglass-logger | ✅ | ✅ | ❌ entries 缺失 | 🟡 有加载路径但无 entries 配置 |

### 6.3 问题：sandglass-logger 缺少 entries 配置

**严重性**: 🟢 低
**说明**: `plugins.allow` 中包含 `sandglass-logger`，`load.paths` 也加载了它，但在 `plugins.entries` 中没有对应的配置。如果插件不需要配置则无影响。

### 6.4 问题：bundledDiscovery 使用 compat 模式

**严重性**: 🟢 低
**说明**: `bundledDiscovery: "compat"` 是旧兼容选项。新版本的 OpenClaw 可能使用其他发现模式。验证最新文档确定当前推荐值。

### 6.5 问题：load.paths 使用自定义路径加载

**严重性**: 🟢 低
**说明**: `load.paths` 指向插件目录路径。确认这两个插件目录中的实际文件结构符合 OpenClaw 插件规范（包含 `plugin.json` 等）。

---

## 七、hooks 配置检查

### 7.1 当前配置

```json5
"hooks": {
  "internal": {
    "enabled": true,
    "entries": {
      "session-memory": { "enabled": true },
      "command-logger": { "enabled": true },
      "pre-compact-memory": { "enabled": false },
      "bootstrap-extra-files": { "enabled": true, "paths": ["AGENTS.md", "SOUL.md", "TOOLS.md", "IDENTITY.md", "USER.md"] }
    }
  }
}
```

### 7.2 评估

| Hook | 状态 | 问题 |
|------|------|------|
| `session-memory` | ✅ 启用 | — |
| `command-logger` | ✅ 启用 | — |
| `pre-compact-memory` | ❌ 禁用 | 🟢 如果不需要可禁用 |
| `bootstrap-extra-files` | ✅ 启用 | — |

### 7.3 注意：bootstrap-extra-files 缺少 BOOT.md 和 HEARTBEAT.md

**说明**: `bootstrap-extra-files.paths` 包含 5 个文件。官方推荐的文件列表中包含 HEARTBEAT.md（可选心跳清单）和 BOOT.md（重启检查清单）。当前列表不含这两个文件，但如果工作区中有这些文件，它们可能仍被其他机制注入。

**建议**: 如果工作区已包含 BOOT.md 和 HEARTBEAT.md，考虑将其加入 paths 列表：
```json5
"paths": ["AGENTS.md", "SOUL.md", "TOOLS.md", "IDENTITY.md", "USER.md", "BOOT.md"]
```

---

## 八、session 配置检查

### 8.1 当前配置

```json5
"session": {
  "scope": "per-sender",
  "dmScope": "main",
  "reset": { "mode": "idle", "idleMinutes": 10080 },
  "resetByType": {
    "direct": { "mode": "idle", "idleMinutes": 10080 },
    "group": { "mode": "idle", "idleMinutes": 10080 },
    "thread": { "mode": "idle", "idleMinutes": 10080 }
  }
}
```

### 8.2 评估

| 字段 | 当前值 | 官方建议 | 问题 |
|------|--------|---------|------|
| `scope` | `per-sender` | `per-sender` | ✅ 正确 |
| `dmScope` | `main` | 单用户 ✅ | ✅ 正确（单用户场景） |
| `reset.mode` | `idle` | `daily` (默认) | 🟡 与官方默认不同 |
| `reset.idleMinutes` | 10080 (=7天) | 120 (默认) | 🟡 7天空闲保留期较长 |

### 8.3 问题：无 daily reset + 7天 idle 保留期

**严重性**: 🟡 中
**说明**: 当前配置使用 `mode: "idle"` + 10080 分钟（7 天）的空闲保留期。这意味着：
- 会话不会在每日 4AM 自动重置
- 会话需连续 7 天无对话才会重置
- 压缩后的上下文长期积累

对于单用户私有 AI 助手，这可能是期望行为。但需注意：
1. 长会话意味着更多压缩操作
2. 会话状态累积可能导致上下文水印增加

### 8.4 问题：未配置 session.maintenance

**严重性**: 🟢 低
**说明**: `session.maintenance` 未设置，使用默认值（`pruneAfter: "30d"`, `maxEntries: 500`），通常合理。

---

## 九、gateway 配置检查

### 9.1 当前配置

```json5
"gateway": {
  "port": 17587,
  "mode": "local",
  "bind": "loopback",
  "auth": { "mode": "token", "token": "clw_fnos_2026_17587" }
}
```

### 9.2 评估

| 字段 | 当前值 | 官方建议 | 问题 |
|------|--------|---------|------|
| `port` | 17587 | 18789 (默认) | 🟢 自定义端口 |
| `mode` | `local` | `local` | ✅ 正确 |
| `bind` | `loopback` | `loopback` | ✅ 正确（安全最佳实践） |
| `auth.mode` | `token` | `token` | ✅ 正确 |
| `auth.token` | `clw_fnos_2026_17587` | 应有 token | ✅ 正确 |
| `controlUi.allowedOrigins` | `["*"]` | 应限制 | 🟡 过于宽松 |
| `tools.allow` | `["sessions_send"]` | 按需设置 | 🟢 合理 |

### 9.3 问题：controlUi.allowInsecureAuth 和 dangerouslyDisableDeviceAuth 同时启用

**严重性**: 🟡 中
**说明**: `allowInsecureAuth: true` 和 `dangerouslyDisableDeviceAuth: true` 同时启用，使用户认证被完全绕过。名称中的 `dangerously` 已表明风险。

**修复建议**: 如果这是单用户本地部署且通过 tailscale/TLS 保护，可以保留。如果暴露在局域网或公网，应启用设备认证。

### 9.4 问题：controlUi.allowedOrigins 为 ["*"]

**严重性**: 🟡 中
**说明**: `allowedOrigins: ["*"]` 允许任意来源通过 CORS 访问控制面板。如果 UI 不在 TLS 保护下，这是一个安全风险。

**修复建议**:
```json5
"allowedOrigins": ["http://localhost:18789", "http://127.0.0.1:18789"]
```

---

## 十、MCP 配置检查

### 10.1 当前配置

```json5
"mcp": {
  "servers": {
    "dandan": {
      "command": "/vol1/.../dandan-mcp-server.mjs",
      "args": [""],
      "enabled": true
    },
    "sandglass": {
      "command": "python3",
      "args": ["/vol2/.../sandglass_mcp.py"],
      "enabled": true
    }
  },
  "sessionIdleTtlMs": 30000
}
```

### 10.2 评估

| 字段 | 当前值 | 问题 |
|------|--------|------|
| `dandan.args` | `[""]` | 🟡 包含空字符串参数，可能引发意外行为 |
| `sessionIdleTtlMs` | 30000 (30秒) | 🟡 低于默认 600000ms（10分钟），MCP 会话可能过快过期 |

### 10.3 问题：dandan MCP 参数含空字符串

**严重性**: 🟡 中
**说明**: `args: [""]` 会向 MCP 服务器传递一个空字符串参数。如果 MCP 服务器不预期此参数，可能导致启动警告或错误。

**修复建议**:
```json5
"dandan": {
  "command": "/vol1/.../dandan-mcp-server.mjs",
  "args": [],  // 移除空字符串
  "enabled": true
}
```

### 10.4 问题：sessionIdleTtlMs 过短

**严重性**: 🟢 低
**说明**: 30秒的 MCP 会话空闲 TTL 非常短。如果工具调用间隔较长，MCP 连接可能被过早关闭。

---

## 十一、workspace 检查

### 11.1 工作区结构

```
workspace/
├── AGENTS.md          ✅ 主要规则
├── SOUL.md            ✅ 人格定义
├── TOOLS.md           ✅ 本地工具说明
├── IDENTITY.md        ✅ 身份定义
├── USER.md            ✅ 用户定义
├── BOOT.md            ✅ 启动检查清单
├── HEARTBEAT.md       ✅ 心跳检查清单
├── MEMORY.md          ✅ 长期记忆
├── BOOTSTRAP.md       ❌ 遗留文件（首次运行后应删除）
├── DREAMS.md          ✅ 梦境日记
├── memory/
│   ├── YYYY-MM-DD.md  ✅ 每日记忆
│   ├── .awake.md      ✅ 唤醒文件
│   ├── facts.dict.md  ✅ 事实索引
│   └── ...
├── dandan-mcp-server.mjs  ✅ MCP 服务端
└── ...
```

### 11.2 问题：BOOTSTRAP.md 遗留

**严重性**: 🟡 中
**说明**: `BOOTSTRAP.md` 是首次运行的一次性引导脚本。根据官方 `start/bootstrapping.md`：
> "Removes BOOTSTRAP.md when finished so it only runs once."

该文件仍在工作区中，表明首次引导可能未完成，或引导后未被自动清理。

**修复建议**: 如果首次引导已完成，安全删除：
```bash
rm /vol1/@apphome/trim.openclaw/data/workspace/BOOTSTRAP.md
```

### 11.3 问题：工作区包含 GGUFP 文件

**严重性**: 🟢 低
**说明**: 工作区根目录包含两个大型 GGUF 模型文件（`bge-m3-Q2_K.gguf` 366MB, `bge-m3-Q4_K_M.gguf` 437MB）。建议将其移到工作区外的模型目录，避免占用工作区空间和被记忆索引误索引。

---

## 十二、doctor 诊断结果

`openclaw doctor` 报告以下需关注的问题：

| 问题 | 严重性 |
|------|--------|
| 🔴 `agents/deepseek/agent/models.json` 中 DeepSeek 缺少 apiKey | 🔴 高 |
| 🟡 遗留 config-health.json 与 SQLite 状态冲突 | 🟡 中 |
| 🟡 NODE_COMPILE_CACHE 未设置（低功耗主机建议设置） | 🟢 建议 |
| 🟡 未配置命令所有者 (command owner) | 🟡 中 |
| 🟡 OPENCLAW_NO_RESPAWN 未设为 1 | 🟢 建议 |

### 12.1 问题：deepseek agent 的 models.json 缺少 apiKey

**严重性**: 🔴 高
**说明**: `agents/deepseek/agent/models.json` 中自定义了 DeepSeek provider 但没有设置 apiKey。这会导致模型注册表加载失败。

**修复建议**: 在 `~/.openclaw/agents/deepseek/agent/models.json` 的 `providers.DeepSeek` 中添加 apiKey：
```json
"DeepSeek": {
  "baseUrl": "https://api.deepseek.com",
  "api": "openai-completions",
  "apiKey": "${DEEPSEEK_API_KEY}",
  ...
}
```

或者删除此文件，让 deepseek agent 只使用 `openclaw.json` 中的全局模型配置。

### 12.2 问题：未配置命令所有者

**严重性**: 🟡 中
**说明**: 未设置 command owner，意味着某些保护性命令（如 `/diagnostics`, `/export-trajectory`, `/config`）和 exec 审批可能不可用或需要额外的认证步骤。

---

## 十三、升级建议

当前运行的二进制是 `2026.6.9`，缓存中存在 `2026.6.11`。以下是关键升级因素：

| 项目 | 当前版本 | 最新缓存版本 | 影响 |
|------|---------|-------------|------|
| OpenClaw 主程序 | 2026.6.9 | 2026.6.11 | 🟡 有 2 个小版本差异 |
| 运行时 | Node 22 | Node 24 (推荐) | 🟡 Node 22 兼容但 24 推荐 |

**升级注意事项**:
1. `bundledDiscovery: "compat"` 在更新后可能需要改为新版发现模式
2. 检查各插件与新版本的兼容性
3. 备份 `~/.openclaw/` 和 workspace 后再升级

---

## 十四、汇总与优先级排序

### 🔴 高优先级（必须修复）

| # | 问题 | 位置 | 修复方案 |
|---|------|------|---------|
| 1 | API Key 明文硬编码 (4 个 provider) | `openclaw.json` | 改为 `${VAR}` 环境变量引用 |
| 2 | deepseek agent 的 models.json 缺少 apiKey | `agents/deepseek/agent/models.json` | 添加 apiKey 或删除文件 |
| 3 | BOOTSTRAP.md 遗留 | 工作区根目录 | 删除或确认引导完成 |

### 🟡 中优先级（建议修复）

| # | 问题 | 位置 | 修复方案 |
|---|------|------|---------|
| 4 | dandan MCP args 含空字符串 | `mcp.servers.dandan.args` | 改为 `[]` |
| 5 | controlUi 安全设置过于宽松 | `gateway.controlUi.*` | 限制 allowedOrigins |
| 6 | 未配置命令所有者 | 全局 | 配置 DM pairing 或 command owner |
| 7 | 遗留 config-health.json 冲突 | `logs/config-health.json` | 运行 `openclaw doctor --fix` |

### 🟢 低优先级（最佳实践）

| # | 问题 | 位置 | 修复方案 |
|---|------|------|---------|
| 8 | 启用 MMR 和 Temporal Decay | `memorySearch.query.hybrid` | 添加上面的可选配置 |
| 9 | session MCP TTL 30秒过短 | `mcp.sessionIdleTtlMs` | 考虑增加到 60000+ |
| 10 | main agent 缺少 name 字段 | `agents.list[0]` | 添加 `name: "..."` |
| 11 | GGUF 模型文件在工作区 | 工作区根目录 | 移出到独立目录 |

---

## 十五、最佳实践总结

### 安全
- ✅ gateway 绑定 loopback
- ✅ 使用 auth token
- ✅ 环境变量引用部分 API Key（混元、智谱）
- ❌ 4 个 provider API Key 明文存储

### 配置完整性
- ✅ agents.list 定义了 main 和 deepseek
- ✅ 使用默认 compaction 配置
- ✅ memorySearch 已启用
- ✅ plugins 正确配置
- ✅ hooks 已启用（含 bootstrap 注入）

### 优化建议
1. 将所有 API Key 移至环境变量
2. 定期运行 `openclaw doctor --fix`
3. 备份 `~/.openclaw/` 和工作区
4. 考虑开启 memorySearch MMR + Temporal Decay
5. 考虑升级到 Node 24

---

> 审计完成于 2026-07-01 11:18 CST
> 本次审计未修改任何配置。修复需 dandan 确认后手动执行。
