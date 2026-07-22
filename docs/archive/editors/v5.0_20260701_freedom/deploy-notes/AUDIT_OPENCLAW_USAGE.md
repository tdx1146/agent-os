# OpenClaw 配置与用法审计报告

> **审计日期**: 2026-07-01
> **审计范围**: 对照 OpenClaw 官方文档，检查当前配置和用法
> **审计对象**: `/vol1/@apphome/trim.openclaw/data/home/.openclaw/openclaw.json`
> **文档版本**: OpenClaw bundled docs (node_modules/openclaw/docs/)

---

## 目录

1. [Workspace 路径与软链问题](#-问题1workspace-路径与软链问题)
2. [Memory 刷写失败（Pre-Compaction Flush）](#-问题2memory-刷写失败pre-compaction-flush)
3. [Compaction 配置（会话压缩）](#-问题3compaction-配置会话压缩)
4. [Agent 模型配置](#-问题4agent-模型配置)
5. [MemorySearch 配置](#-问题5memorysearch-配置)
6. [Inject-Helper 与子代理通道](#-问题6inject-helper-与子代理通道)
7. [Skills / Hooks / Cron 用法](#-问题7skills--hooks--cron-用法)
8. [会话安全](#-问题8会话安全)
9. [其他发现](#-问题9其他发现)
10. [总结与优先级排序](#-总结与优先级排序)

---

## ❌ 问题1：Workspace 路径与软链问题

【违规范畴】安全隐患 / 配置不当

【当前做法】
```
workspace: "/vol1/@apphome/trim.openclaw/data/workspace"
```
- `memory/` 目录为软链：`workspace/memory → /轻如烟/memory/`
- 用户组：软链目标 owner 为 `tdx1146:Users`，与 gateway 用户 `trim.openclaw` 不同
- `write` 工具报错：`Symlink escapes sandbox root`

【文档预期】
- **agent-workspace.md**: "The workspace is the agent's home. It is the only working directory used for file tools and for workspace context."
- **agent-workspace.md**: Workspace 下 `memory/YYYY-MM-DD.md` 是标准 daily memory log 位置
- **agent-workspace.md > Note**: "Sandbox seed copies only accept regular in-workspace files; symlink/hardlink aliases that resolve outside the source workspace are ignored."
- **secure-file-operations.md**: fs-safe 默认拒绝 symlink/hardlink patterns："refusing symlink and hardlink patterns on APIs that require that policy"
- **security/audit-checks.md**: `skills.workspace.symlink_escape` - warn level check for symlinks escaping workspace
- **security/index.md > Local disk hygiene**: mentions "permissions, symlinks, config includes, 'synced folder' paths" as audit items

【文档来源】
- `concepts/agent-workspace.md`: 第 39 行（sandbox seed 拒绝跨 workspace symlinks）
- `gateway/security/secure-file-operations.md`: "refusing symlink and hardlink patterns"
- `gateway/security/audit-checks.md`: `skills.workspace.symlink_escape` checkId
- `gateway/security/index.md`: 第 244 行 "Local disk hygiene" 包含 symlinks

【差距分析】
1. **违反安全模型**: fs-safe 安全层拒绝跨沙箱根目录的 symlink。`memory/` 指向 `/轻如烟/memory/` 逃逸了 workspace 根目录，触发 fs-safe 的路径安全保护
2. **违反目录预期**: 文档明确说明 workspace 是 agent 的家目录，所有文件操作都在此空间内。软链到外部路径破坏了这一约定
3. **跨用户权限问题**: gateway 以 `trim.openclaw` 运行，软链目标由 `tdx1146:Users` 管理。文件操作可能出现权限不一致
4. **`write` 工具不可用**: 由于 fs-safe 的安全策略，通过 `write` 工具写入 `memory/` 下的任何文件都会失败
5. **无法自动备份**: 文档建议 `git add AGENTS.md SOUL.md TOOLS.md ... memory/` 将 `memory/` 纳入版本管理，软链导致这一模式断裂

【修正建议】
- **推荐方案**: 移除软链，将 workspace `memory/` 作为真实目录。通过外部同步机制（如 rsync/cron）将 `memory/` 内容同步到 `/轻如烟/memory/`
  ```bash
  rm /vol1/@apphome/trim.openclaw/data/workspace/memory
  mkdir /vol1/@apphome/trim.openclaw/data/workspace/memory
  chown trim.openclaw:trim.openclaw /vol1/@apphome/trim.openclaw/data/workspace/memory
  # 添加 cron：rsync -av /vol1/@apphome/trim.openclaw/data/workspace/memory/ /轻如烟/memory/
  ```
- **备选方案（如果必须共享）**: 将 `/轻如烟/memory/` 改为 bind mount 到 workspace 下，但需要在 gateway 启动前完成。或者直接将 workspace 指向外部路径，但需要保证 write 权限。

---

## ❌ 问题2：Memory 刷写失败（Pre-Compaction Flush）

【违规范畴】配置不当 / 功能异常

【当前做法】
- OpenClaw 自动 memory flush（compaction 前的静默 memory 写入）尝试写 `memory/YYYY-MM-DD.md`
- 因 `memory/` 为软链（问题1），flush 失败
- 未配置 `compaction.memoryFlush` 的任何参数

【文档预期】
- **compaction.md**: "Before compacting, OpenClaw automatically reminds the agent to save important notes to memory files."
- **config-agents.md**: compaction 下可配置 `memoryFlush`:
  ```json5
  memoryFlush: {
    enabled: true,
    model: "ollama/qwen3:8b",
    softThresholdTokens: 6000,
    systemPrompt: "Session nearing compaction. Store durable memories now.",
    prompt: "Write any lasting notes to memory/YYYY-MM-DD.md; reply with the exact silent token NO_REPLY if nothing to store.",
  }
  ```
- **compaction.md > memoryFlush**: "Skipped when workspace is read-only."
- **session-management-compaction.md**: `memoryFlushAt` timestamp 和 `memoryFlushCompactionCount` 是 session store 中的跟踪字段

【文档来源】
- `concepts/compaction.md`: Auto-compaction → memory flush 段
- `gateway/config-agents.md`: `compaction.memoryFlush.*` 配置段，第 648-655 行
- `reference/session-management-compaction.md`: `memoryFlushAt`, `memoryFlushCompactionCount`

【差距分析】
1. **根本原因同问题1**: memory flush 通过 `write` 工具写入 `memory/YYYY-MM-DD.md`，但软链导致写入失败
2. **未显式配置 memoryFlush**: 即使修复软链，当前配置也未启用 `memoryFlush` 的任何调优参数（默认 enabled: true，但无 model override，无 softThresholdTokens）
3. **默认行为问题**: 当 memory flush 失败时，文档未明确说明 fallback 行为。可能导致 compaction 前上下文丢失
4. **无模型覆盖**: 默认使用主对话模型进行 flush，在 1M 上下文中浪费高成本 DeepSeek V4 调用用于简单的笔记写入

【修正建议】
1. **先修复问题1**（移除软链）
2. **优化 memoryFlush 配置**:
   ```json5
   agents: {
     defaults: {
       compaction: {
         memoryFlush: {
           enabled: true,
           softThresholdTokens: 16000,
           prompt: "Write any lasting notes to memory/YYYY-MM-DD.md with timestamp; reply NO_REPLY if nothing changed.",
         },
       },
     },
   }
   ```
3. **验证**: 修复后执行一次 compaction 触发，检查 `memory/2026-07-01.md` 是否正常写入

---

## ❌ 问题3：Compaction 配置（会话压缩）

【违规范畴】配置不当（默认值未优化）

【当前做法】
- 未配置任何 `compaction` 参数，完全使用默认值
- 默认值：`reserveTokens: 16384`，`keepRecentTokens: 20000`
- safety floor: `20000`（文档明确标注）
- 上下文窗口：1,000,000（1M）
- 已运行 6 天，10 次压缩

【文档预期】
- **session-management-compaction.md > reserveTokens**: 16384 是默认值，但 safety floor 是 20000
- **session-management-compaction.md**: "OpenClaw also enforces a safety floor for embedded runs: If `compaction.reserveTokens < reserveTokensFloor`, OpenClaw bumps it. Default floor is `20000` tokens."
- **config-agents.md** 示例配置使用: `reserveTokensFloor: 24000`, `keepRecentTokens: 50000`
- **compaction.md**: reserveTokens 是模型输出所需的 headroom。对于大型工具调用场景需要更多
- **session-management-compaction.md**: `contextTokens > contextWindow - reserveTokens` 时触发

【文档来源】
- `reference/session-management-compaction.md`: 第 297-330 行（reserveTokens, keepRecentTokens, safetyFloor）
- `gateway/config-agents.md`: 第 634-655 行（compaction 配置示例）
- `concepts/compaction.md`: 全文

【差距分析】

| 参数 | 当前值 | 推荐值 | 理由 |
|------|--------|--------|------|
| `reserveTokens` | 16384 (默认) | 24000-32000 | 1M 窗口下，16K headroom 太紧。工具 schema + 输出 + 提示头约 10-20K |
| `keepRecentTokens` | 20000 (默认) | 50000-80000 | 压缩保留的最近会话太少，约 20000 token ≈ 少数几个上下文轮次 |
| `reserveTokensFloor` | 20000 (默认 floor) | 24000 | 文档示例直接用 24000，对 1M 更合理 |
| `truncateAfterCompaction` | false (默认) | true | 不轮转则 JSONL 持续增长，影响启动加载速度 |
| `notifyUser` | false (默认) | true | 6 天 10 次压缩无通知，用户完全不知情 |
| `mode` | default (默认) | safeguard | 1M 上 safeguard 模式分块压缩更可靠 |

**计算**: 在 1M contextWindow 下：
- 当前触发阈值: 1,000,000 - 16,384 = 983,616 tokens
- 建议触发阈值: 1,000,000 - 24,000 = 976,000 tokens
- keepRecentTokens 从 20K 提升到 50K 意味着压缩后保留 ~125% 更多最近对话

6 天 10 次压缩 ≈ 每 14.4 小时一次，频率合理。但保留内容太少可能影响对话质量。

【修正建议】
```json5
{
  agents: {
    defaults: {
      compaction: {
        mode: "safeguard",
        timeoutSeconds: 180,
        reserveTokensFloor: 24000,
        keepRecentTokens: 50000,
        identifierPolicy: "strict",
        qualityGuard: { enabled: true, maxRetries: 1 },
        truncateAfterCompaction: true,
        notifyUser: true,
        memoryFlush: {
          enabled: true,
          softThresholdTokens: 16000,
        },
      },
    },
  },
}
```

---

## ❌ 问题4：Agent 模型配置

【违规范畴】配置不当 / 安全隐患 / 文档理解偏差

### 4a. API Key 明文存储

【当前做法】
- `openclaw.json` 中直接明文写入三个 provider 的 `apiKey`：
  - DeepSeek: `sk-f345bded2ccd4f468f059b53336a832c`
  - 混元: `sk-tp-Y24HbUPdadeOVjnD8QEVRW1FTA7emtyzC6CppuAQDSW1fNCD`
  - astron廉价: `c318e18b3695cb32418fa1c11a1a9b6d:MjFkM2VjZTMyYTQzOTlhZDVlZTNiZjA2`

【文档预期】
- **authentication.md**: "API key auth is still the most predictable server setup" 但推荐通过环境变量或 `~/.openclaw/.env` 管理
- **authentication.md**: 推荐: `export DEEPSEEK_API_KEY="..."` 或放入 `~/.openclaw/.env`
- **security/index.md**: "config may include tokens (gateway, remote gateway), provider settings, and allowlists" 属于需要保护的内容
- **security/index.md**: "Keep permissions tight (700 on dirs, 600 on files)" 但明文在 config 中即使权限正确仍属暴露

【文档来源】
- `gateway/authentication.md`: "Recommended setup (API key, any provider)"
- `gateway/security/index.md`: "Secrets on disk" 段，第 ~380 行
- `gateway/secrets.md`: SecretRef 机制

### 4b. DeepSeek 自定义 Provider 覆盖内置 Catalog

【当前做法】
```json
"deepseek": {
    "api": "openai-completions",
    "baseUrl": "https://api.deepseek.com",
    "apiKey": "sk-...",
    "models": [
      {
        "id": "deepseek-v4-flash",
        "input": ["text", "image"],  // ❸ image 类型标注错误
        "contextWindow": 1000000,
        "maxTokens": 384000
      },
      {
        "id": "deepseek-v4-pro",
        "input": ["text", "image"],  // ❸ image 类型标注错误
        "contextWindow": 1000000,
        "maxTokens": 384000
      }
    ]
}
```

【文档预期】
- **providers/deepseek.md** Built-in catalog 表: DeepSeek V4 Flash/Pro 的 Input 为 `text`，不是 `["text", "image"]`
- 文档没有说明 DeepSeek V4 支持图像输入。标注 `input: ["text", "image"]` 会导致 OpenClaw 认为该模型支持图像，从而向 DeepSeek API 发送图像数据
- **config-tools.md**: "Matching model `contextWindow`/`maxTokens` use the higher value between explicit config and implicit catalog values."
- 自定义 `deepseek` provider id 与内置 `deepseek` provider id 冲突。内置 catalog 中的 `deepseek/deepseek-v4-flash` 会被自定义覆盖

### 4c. 缺少 `models.mode` 配置

【当前做法】
- 未设置 `models.mode`，默认使用 `merge`
- 自定义 provider `deepseek` 与内置 `deepseek` provider id 冲突

【文档预期】
- **config-tools.md**: `models.mode` 决定 provider catalog 行为：`merge` 或 `replace`
- 当内置 catalog 已有 `deepseek` provider 时，自定义的 `deepseek` provider 会 merge（合并）进去，可能导致重复或冲突

### 4d. Astron 和 混元 缺少 `contextWindow` / `maxTokens`

【当前做法】
```json
"混元": {
    "models": [{ "id": "hy3-preview", "input": ["text"] }]  // 无 contextWindow, 无 maxTokens
},
"astron廉价": {
    "models": [{ "id": "astron-code-latest", "input": ["text"] }]  // 无 contextWindow, 无 maxTokens
}
```

【文档预期】
- **config-tools.md**: "`models.providers.*.models.*.contextWindow`: native model context window metadata"
- **config-tools.md**: "`models.providers.*.models.*.maxTokens`: output-token cap"
- 未设置时 OpenClaw 无法知悉模型上下文窗口上限，可能导致请求超出模型实际能力

### 4e. `imageModel` 指向不支持图像输入的模型

【当前做法】
```json
"imageModel": "deepseek/deepseek-v4-flash"
```

【文档预期】
- 内置 catalog 中 DeepSeek V4 Flash Input 为 `text` 非 `text,image`
- `config-tools.md`: "Image attachments are only injected into agent turns when the selected model is marked image-capable"
- 即使自定义 catalog 错误地标注了 `["text", "image"]`，实际 DeepSeek API 也不接受图像输入，会导致 API 调用失败

【文档来源】
- `providers/deepseek.md`: Built-in catalog 表
- `gateway/config-tools.md`: Provider field details, `models.providers.*.models.*.input`
- `gateway/authentication.md`: API key 管理
- `gateway/security/index.md`: 密钥管理

【差距分析汇总】

| 子问题 | 严重程度 | 影响 |
|--------|---------|------|
| 4a. API Key 明文 | 🔴 高 | 任何有能力读 config 的人可获取所有 provider 的密钥 |
| 4b. image 标注错误 | 🟡 中 | 可能触发 OpenClaw 向 DeepSeek 发送图像，API 报错或静默失败 |
| 4c. models.mode 未设置 | 🟢 低 | merge 模式可能与内置 catalog 冲突，但当前工作 |
| 4d. 缺少 contextWindow | 🟡 中 | 混元/astron 模型的行为不可预测，可能意外溢出 |
| 4e. imageModel 错配 | 🟡 中 | 图像处理功能实际上不可用 |

【修正建议】
1. **移除 API keys**: 从 config 中删除所有 `apiKey` 行，改用 `~/.openclaw/.env`：
   ```
   DEEPSEEK_API_KEY=sk-...
   ```
   或使用 SecretRef 机制
2. **修正 DeepSeek 模型 input**:
   ```json
   "models": [
     {
       "id": "deepseek-v4-flash",
       "input": ["text"],  // 移除 "image"
       ...
     }
   ]
   ```
3. **添加 contextWindow/maxTokens 到所有自定义模型**
4. **移除 `imageModel`** 或指向真正支持图像的模型（如混元，如果支持）
5. **考虑简化**: 如果使用内置 catalog 已经够用，完全移除自定义 deepseek provider，让 OpenClaw 使用内置 catalog

---

## ❌ 问题5：MemorySearch 配置

【违规范畴】文档理解偏差 / 功能受限

【当前做法】
```json
"memorySearch": {
    "provider": "none"
}
```
- 仅使用 FTS5 全文搜索，无向量嵌入
- 当初设置 "none" 的理由是对应文档中"不需要 embeddings 时用 none"

【文档预期】
- **memory-builtin.md**: "Without an embedding provider, only keyword search is available."
- **memory-search.md**: "Intentional FTS-only mode (`provider: "none"`) and automatic/default provider selection can still use lexical ranking when embeddings are unavailable."
- **memory-config.md**: `provider: "none"` intentionally selects FTS-only mode
- **memory-config.md > "Explicit non-local providers fail closed"**: 但 `none` 不是 remote-backed provider，所以可以正常工作

【文档来源】
- `concepts/memory-builtin.md`: 第 ~30 行
- `concepts/memory-search.md`: "How search works" 段
- `reference/memory-config.md`: Provider selection 表

【差距分析】
1. **配置语法正确**: `provider: "none"` 在文档中有明确定义，是合法的 FTS-only 模式
2. **但功能严重受限**: FTS5 全文搜索只能精确匹配关键词，不支持语义搜索
   - 对于中文（CJK），FTS5 trigram 分词效果一般
   - 无法找到"意思相近但用词不同"的内容
   - 无向量搜索意味着无 MMR（多样性增强）、无 temporal decay（时间衰减）
3. **DeepSeek 本身无 embedding API**: 无法通过现有 deepseek provider 提供向量搜索
4. **错过可用方案**: 可以对自建 Ollama embedding 端点，或使用 Gemini Embedding API

【修正建议】
- **方案 A（推荐，无外部依赖）**: 安装本地 GGUF embedding:
  ```bash
  openclaw plugins install @openclaw/llama-cpp-provider
  ```
  配置：
  ```json5
  {
    agents: {
      defaults: {
        memorySearch: {
          provider: "local",
          fallback: "none",
          local: {
            modelPath: "~/.node-llama-cpp/models/your-embedding-model.gguf",
          },
          query: {
            hybrid: {
              mmr: { enabled: true, diversity: 0.3 },
              temporalDecay: { enabled: true, halfLifeDays: 30 },
            },
          },
        },
      },
    },
  }
  ```
- **方案 B**: 使用 Ollama embedding（如果已有 Ollama）:
  ```json5
  {
    memorySearch: {
      provider: "ollama",
      model: "qwen3-embedding:0.6b",
      fallback: "none",
    },
  }
  ```
- **方案 C（如果 FTS-only 已满足需求）**: 保留 `provider: "none"` 但增加额外调优:
  ```json5
  {
    memorySearch: {
      provider: "none",
      query: {
        hybrid: {
          mmr: { enabled: true },
          temporalDecay: { enabled: true },
        },
      },
    },
  }
  ```

---

## ❌ 问题6：Inject-Helper 与子代理通道

【违规范畴】非标准用法

【当前做法】
- 通过 SSH + `inject-helper.mjs` HTTP POST 通道向 OpenClaw 实例发送注入
- 部署指南 (`v5.0_DEPLOY_GUIDE.md`) 中描述为 "OpenClaw 注入通道"
- 文件位于 workspace 目录，通过 Node.js HTTP 服务暴露

【文档预期】
- OpenClaw 官方子代理通信机制：
  - **`sessions_spawn`** 工具: 生成子代理会话
  - **`sessions_send`** 工具: 向子代理发送消息
  - **`sessions_yield`** 工具: 等待子代理完成并获取结果
  - **MCP (Model Context Protocol)**: 标准化的工具/资源暴露协议（`mcp.servers` 配置）
  - **Webhooks**: 外部 HTTP 触发 Gateway 事件
  - **Hooks**: 内部事件驱动自动化
- **config-agents.md**: `subagents.allowAgents` 配置子代理的 agent id 许可

【文档来源】
- `gateway/config-agents.md`: `subagents.*`, `sessions_spawn`, `sessions_send` 配置段
- `reference/session-management-compaction.md`: sessions_spawn 和 sessions_send 是内置工具
- `automation/hooks.md`: 内部 hooks 系统
- `automation/cron-jobs.md`: 外部 webhooks

【差距分析】
1. **非标准方案**: `inject-helper.mjs` 不是 OpenClaw 官方定义的任何组件或扩展点。文档中不存在 `inject-helper`、`injectHelper`、`submit-helper` 等概念
2. **绕过安全模型**: 任何有 SSH 访问权限的进程都可以通过 HTTP POST 注入内容，绕过了 OpenClaw 的 channel 认证、DM 策略、allowlist 等安全控制
3. **无官方支持**: 使用非标准方式意味着 OpenClaw 升级可能导致方案失效；也无法获得社区支持和文档
4. **维护成本**: 团队需要自己维护 `inject-helper.mjs` 的兼容性

【修正建议】
- **方案 A（推荐）**: 使用 OpenClaw 内置的 sessions_spawn/sessions_send/sessions_yield 工具链
  ```javascript
  // 在 AGENTS.md 中通过指令告知主 agent 使用 sessions_spawn
  // 或通过 hooks 实现自动化注入
  ```
- **方案 B**: 使用 Webhooks（如果注入来自外部系统）
  ```json5
  {
    hooks: {
      token: "your-hook-token",
      allowedAgentIds: ["main"],
      paths: { "/inject": { agentId: "main" } },
    },
  }
  ```
- **方案 C（保留但不推荐）**: 如果必须保留 inject-helper，至少增加：
  - token 认证
  - HTTPS 而非 HTTP
  - 绑定到 loopback 而非开放端口
  - 记录到 gateway 日志

---

## ❌ 问题7：Skills / Hooks / Cron 用法

【违规范畴】功能未充分利用（文档已提供但未使用）

【当前做法】
- Skills: 有一个 skill ```senior-assistant-orchestrator``` 配置在工作区 `skills/` 目录下
- Hooks: `hooks/` 目录已创建但为空
- Cron: 未配置任何 cron job
- 使用了 `skill_workshop` 工具

【文档预期】
- **hooks.md**: Hooks 支持以下事件: `command:new`, `command:reset`, `session:compact:before`, `session:compact:after`, `gateway:startup`, `gateway:shutdown`, `message:received`, `message:sent` 等
- **automation/cron-jobs.md**: 支持定时任务配置
- **config-agents.md**: `cron.jobs[]` 配置定时任务
- **hooks.md > internal hooks**: 支持自动启动任务（`gateway:startup` event）

【文档来源】
- `automation/hooks.md`: 事件类型表
- `automation/cron-jobs.md`: cron 配置参考
- `gateway/config-agents.md`: cron.* 配置

【差距分析】
1. **Skills 使用正确**: `skill_workshop` 是文档化的功能，`skills/` 目录也是官方支持的位置。用法预期一致 ✓
2. **Hooks 未充分利用**: 
   - 已创建 `hooks/` 目录但无任何 handler
   - 未使用 `gateway:startup` 事件实现开机自启动任务
   - 未使用 `session:compact:before/after` 事件监控 compaction
3. **Cron 未配置**:
   - 无定时任务（如定期清理、定期备份、定期自检）
   - 文档支持的 `cron.jobs[]` 功能完全未使用

【修正建议】
```json5
{
  cron: {
    jobs: [
      {
        id: "daily-health-check",
        schedule: "0 8 * * *",
        agentId: "main",
        prompt: "Run a quick health check. Check: (1) disk space on /vol1, (2) gateway is running, (3) searxng is reachable, (4) memory files are writable. Report only if something is wrong.",
        sessionTarget: "isolated",
      },
      {
        id: "daily-memory-backup",
        schedule: "0 3 * * *",
        agentId: "main",
        prompt: "Review today's memory entries and ensure MEMORY.md is up to date. Write a brief status update.",
        sessionTarget: "isolated",
      },
    ],
  },
}
```

以及 hooks：
```
hooks/
├── BOOT.md              # gateway:startup 自动启动
└── compact-notify/      # session:compact:after 事件通知
    ├── HOOK.md
    └── handler.ts
```

---

## ❌ 问题8：会话安全

【违规范畴】安全隐患

### 8a. 危险 Control UI 配置

【当前做法】
```json
"controlUi": {
    "enabled": true,
    "basePath": "/app/trim-openclaw/default",
    "allowInsecureAuth": true,
    "dangerouslyDisableDeviceAuth": true,
    "allowedOrigins": ["*"]
}
```

【文档预期】
- **security/index.md > Insecure or dangerous flags summary**:
  - `gateway.controlUi.allowInsecureAuth=true` — 被跟踪的危险标志
  - `gateway.controlUi.dangerouslyDisableDeviceAuth=true` — "severe security downgrade"
  - `gateway.controlUi.allowedOrigins: ["*"]` — "explicit allow-all browser-origin policy, not a hardened default"
- **security/index.md > Control UI over HTTP**: "The Control UI needs a secure context (HTTPS or localhost) to generate device identity."
- **security/audit-checks.md**: `gateway.control_ui.insecure_auth` (warn), `gateway.control_ui.device_auth_disabled` (critical), `gateway.control_ui.allowed_origins_wildcard` (warn/critical)

【文档来源】
- `gateway/security/index.md`: Insecure or dangerous flags 段（~第 220 行）
- `gateway/security/audit-checks.md`: `gateway.control_ui.*` checkIds

### 8b. Session Reset 配置过长

【当前做法】
```json
"session": {
    "reset": {
        "mode": "idle",
        "idleMinutes": 43200
    }
}
```

43200 分钟 = 30 天。30 天没有活动才自动 reset session。

【文档预期】
- **session-management-compaction.md**: session.reset.mode 支持 idle 模式
- 无明确的"推荐空闲时间"，但 30 天的 idle 窗口意味着 session 几乎不会被自动清理
- 1M context 运行在同一个 session 中 30 天，即使间隔使用也不会重置

### 8c. API Keys 明文存储（已在问题4中覆盖，这里聚焦安全）

【当前做法】
- gateway token: `74127b15c6674fccb92bd69adc2113a1` 明文在 config
- 三个 provider API keys 明文在 config

【文档预期】
- **security/index.md**: Config 中的 secrets 建议使用环境变量或 SecretRef
- **config-tools.md**: API keys 建议使用 `~/.openclaw/.env`
- **authentication.md**: API key 推荐通过 gateway host 环境变量管理

【差距分析汇总】

| 子问题 | 严重程度 | 影响 |
|--------|---------|------|
| 8a. dangerouslyDisableDeviceAuth | 🔴 高 | 完全禁用设备身份验证，任何能访问 Control UI 的人可操作 |
| 8a. allowInsecureAuth | 🟡 中 | 允许 HTTP 上进行 auth，增加中间人攻击风险 |
| 8a. allowedOrigins: ["*"] | 🟡 中 | 浏览器跨域策略完全开放，增加 CSRF 类攻击面 |
| 8b. idleMinutes: 43200 | 🟢 低 | 长 session 生命周期，但 OpenClaw 默认即设计为单用户信任模型 |
| 8c. 明文密钥 | 🔴 高 | 读取 config 即可获取所有凭据 |

【修正建议】
1. **移除危险 Control UI 标志**:
   ```json
   "controlUi": {
       "enabled": true,
       "basePath": "/app/trim-openclaw/default",
       "allowInsecureAuth": false,     // 关闭
       "dangerouslyDisableDeviceAuth": false,  // 关闭
       "allowedOrigins": []            // 移除通配符
   }
   ```
   **仅当 Control UI 仅在 tailnet/loopback 使用时才能安全关闭 device auth**。如果必须在外网使用，请正确配置 HTTPS + device auth。
2. **API keys 迁移到 `.env`**:
   ```
   # ~/.openclaw/.env
   DEEPSEEK_API_KEY=sk-...
   OPENCLAW_GATEWAY_TOKEN=74127b15c6674fccb92bd69adc2113a1
   ```
   然后在 config 中移除 `apiKey` 字段，由 OpenClaw 自动检测环境变量。
3. **适当降低 idleMinutes**（如果需要更频繁的 session 轮转）:
   ```json
   "session": {
       "reset": {
           "mode": "idle",
           "idleMinutes": 43200  // 保持 30 天或按需调低
       }
   }
   ```

---

## ❌ 问题9：其他发现

### 9a. Bing/__开悟__ 占位 token 在 config 中

【当前做法】
- `tools.web.search` 配置中使用 `searxng` 作为 provider
- config 中无 `BING_API_KEY` 或类似占位内容

无发现问题。SearXNG 配置符合文档预期 ✓

### 9b. Gateway 端口非默认

【当前做法】
```json
"gateway": {
    "port": 32823,
    "bind": "loopback",
    "trustedProxies": ["127.0.0.1", "::1"]
}
```

非默认端口，但属于合法配置。`trustedProxies` 配置正确限制了 loopback。bind loopback 符合安全推荐。✓

### 9c. 网关 token 无 rate limit 配置

安全审计检查项 `gateway.auth_no_rate_limit` 可能触发 warning。但 bind loopback + 已有 token auth 基本满足单用户场景。

### 9d. searxng 插件配置

```json
"plugins": {
    "entries": {
        "searxng": { ... }
    }
}
```

符合文档要求 ✓

---

## 总结与优先级排序

### 按严重程度排列

| 优先级 | 问题编号 | 标题 | 严重度 | 影响面 | 修复时间 |
|--------|---------|------|--------|--------|---------|
| P0 | 1 | Workspace memory/ 软链 | 🔴 阻塞 | write 工具不可用，memory flush 失败 | 立即 |
| P0 | 2 | Memory flush 失败 | 🔴 阻塞 | compaction 前上下文丢失 | 依赖 P0#1 |
| P0 | 8a | Control UI 危险标志 | 🔴 安全 | 设备身份验证完全禁用 | 立即 |
| P0 | 4a/8c | API Key 明文 | 🔴 安全 | config 泄露后凭据被盗 | 1 小时内 |
| P1 | 4b | DeepSeek image 错误标注 | 🟡 功能 | 可能导致 API 调用失败 | 1 天内 |
| P1 | 6 | inject-helper 非标准 | 🟡 维护 | OpenClaw 升级后兼容风险 | 1-3 天 |
| P1 | 3 | Compaction 默认值未优化 | 🟡 性能 | 1M 下压缩行为不理想 | 1 天内 |
| P2 | 4d | 缺少 contextWindow/maxTokens | 🟢 风险 | 模型行为不可预测 | 按需 |
| P2 | 4e | imageModel 错配 | 🟢 功能 | 图像处理实际上不可用 | 按需 |
| P3 | 5 | MemorySearch FTS-only | 🟢 增强 | 搜索质量受限 | 规划项 |
| P3 | 7 | Hooks/Cron 未使用 | 🟢 增强 | 缺少自动化和监控 | 规划项 |

### 前 3 步行动

1. **立即**: 移除 `workspace/memory` 软链，重建为本地目录；移除 Control UI 危险标志
2. **立即**: 从 `openclaw.json` 移除所有明文 API keys，迁移到 `~/.openclaw/.env`
3. **1 天内**: 添加 compaction 优化配置；修正 DeepSeek 模型 input 标注

### 自动化修正建议

在配置级修改前，建议运行官方安全审计：
```bash
openclaw security audit
openclaw security audit --deep
openclaw security audit --fix
```

---

*审计完成。本报告已在 `/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/deploy-notes/AUDIT_OPENCLAW_USAGE.md` 输出。*
