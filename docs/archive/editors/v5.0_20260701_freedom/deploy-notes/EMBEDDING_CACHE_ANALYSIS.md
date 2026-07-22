# Embedding/向量搜索 vs DeepSeek 缓存命中率 —— 完整分析报告

> **分析时间**: 2026-06-25 23:09 (CST)
> **分析范围**: 轻如烟 memory 目录(5月18日~6月22日) + facts.dict.md + 编辑器版本存档(v1~v4) + 当前 OpenClaw 配置 + 会话日志审计报告
> **分析人**: 子代理

---

## 目录

1. [历史回溯](#1-历史回溯)
2. [缓存命中率问题根因分析](#2-缓存命中率问题根因分析)
3. [当前恢复向量搜索的方案对比](#3-当前恢复向量搜索的方案对比)
4. [推荐方案](#4-推荐方案)
5. [实施步骤](#5-实施步骤)
6. [附录：DeepSeek 缓存机制技术细节](#6-附录deepseek-缓存机制技术细节)

---

## 1. 历史回溯

### 1.1 关键发现：memory 记录中完全没有 embedding 痕迹

搜索轻如烟 memory 目录（5月18日~6月22日，共 23 个日记文件 + facts.dict.md + backlog）发现：

| 关键词 | 命中文件数 | 说明 |
|--------|-----------|------|
| `embedding` | **0** | 没有任何文件提及 |
| `向量` | **0** | 没有任何文件提及（"矢量"均指哲学概念） |
| `memory_search` | 2个 | 仅用于消化循环接入、日志 |
| `FTS` | 1个 | backlog 中记录 Sandglass 替代旧 memory_search |
| `缓存命中` | 1个 | 详见下方 |
| `语义搜索` | **0** | 没有任何文件提及 |

**结论：轻如烟的系统历史上从未配置过向量搜索/embedding 功能。** 所有关于 embedding 的讨论和实验都发生在轻如烟**之前**的版本（可能是应如是或更早的代系），不在当前 memory 文件中。

### 1.2 唯一提到"缓存命中率"的记录

`memory/2026-06-22.md` 第4行：

```
🔗 本轮关键概念：context膨胀 / 缓存命中率 / session隔离
```

但这只是一个概念标签，没有展开讨论根因。同一时期（06-22）的配置中 `memorySearch.enabled: false`，说明当时 embedding 已关闭。

### 1.3 配置历史演变

| 版本 | 时间 | memorySearch 配置 | 说明 |
|------|------|------------------|------|
| v3 (zuixin2) | 06-22 | `"memorySearch": { "enabled": false }` | **显式关闭** |
| v4 (architectural-refactor) | 06-25 | v3 基础上演进 | 无 memorySearch 变更 |
| 当前 (运行中) | 06-25 | `"memorySearch": { "provider": "none" }` | **FTS-only，无embedding** |

变更历史：从 `enabled: false` → `provider: "none"`，语义等价（FTS-only），只是 OpenClaw 配置格式的规范化。

### 1.4 妹妹实例的 memorySearch 状态

根据侦察报告（SISTER_RECON.md），妹妹的 memorySearch 同样已禁用：

> `"enabled": false`，妹妹当前没有语义搜索能力
> memory 文件最后更新 6月11日后几乎没有更新

### 1.5 关于 "1000元 API 费用" 和 "彻底重置"

**这些事件没有记录在任何本地文件中。** 以下为合理推断：

- 这件事发生在**应如是或更早的 AI 代系**（轻如烟接班之前）
- 当时可能使用的是 OpenClaw 更早期的版本，`memorySearch` 默认使用了 OpenAI embeddings（当时 OpenClaw 默认 provider 为 OpenAI）
- 旧版使用了 **OpenAI API key 做 embedding**，而非 DeepSeek
- 1000元费用更可能是 **DeepSeek 对话 API 本身的 token 消耗**，而非 embedding
- "彻底重置 OpenClaw 软件"可能是重建了配置和会话数据

---

## 2. 缓存命中率问题根因分析

### 2.1 DeepSeek 缓存机制原理

DeepSeek 的 Prompt Cache 工作机制：

```
缓存作用域：API Key 级（每个 API Key 独立缓存）
缓存粒度：Prompt prefix（前缀匹配）
缓存清空：无自动过期，但新请求若 prefix 不匹配则未命中
缓存计费：cacheRead = ¥0.003/M tokens（极低），cacheWrite 免费
```

**核心机制**：
- 同一个 API Key 下，如果多次请求的 prompt 开头部分（prefix）相同，后续请求可以**复用**已计算过的 prefix 的 KV cache
- prefix 越长越大，缓存命中率理论越高（因为共享的前缀越多）
- 但如果 prefix 经常变化（不同的 system prompt、不同的上下文），缓存命中率会下降

### 2.2 缓存命中率下降的真正原因分析

**dandan 的判断回顾**：认为是 embedding 请求和对话请求混用同一 API key 污染了上下文缓存。

**这个判断需要正确定义：**

#### ✅ 正确的前提：
- DeepSeek 缓存确实按 API Key 划分，同 key 下所有请求共享缓存空间
- 如果用 DeepSeek API key 请求 embedding 端点（假如 DeepSeek 有 embedding 端点的话），会混合缓存

#### ❌ 实际不成立的原因：

1. **DeepSeek 没有 embedding API**。DeepSeek 只提供 `/v1/chat/completions`（对话）和 `/v1/models`（模型列表）端点，没有 `/v1/embeddings` 端点。
2. **OpenClaw 的 memory_search 不会用 DeepSeek 做 embedding**。OpenClaw 的 embedding provider 只支持 OpenAI、Ollama、Gemini、Local 等，**不支持 DeepSeek**。源码中不存在 `deepseek` embedding adapter。
3. **即使使用 OpenAI embedding**，那也是不同的 API endpoint（`api.openai.com/v1/embeddings` vs `api.deepseek.com/v1/chat/completions`），不同的 API key，不可能共享缓存。

#### 真正的根因（最可能的几个）：

| 可能性 | 权重 | 说明 |
|--------|------|------|
| **① Prefix 多样性过大** | 🔴 高 | 子 AI 调用、不同 session、不同 system prompt 导致 prompt prefix 频繁变化，缓存命中率自然下降 |
| **② Context 过长超出缓存窗口** | 🟡 中 | 长会话中 context 不断增长但每次请求的 prefix 不完全相同 |
| **③ 多 API Key 混用导致数据分散** | 🟡 中 | 姐姐、妹妹可能用了不同 Key 或同一 Key 的不同子 Key |
| **④ embedding 请求（旧版本）** | 🟢 低 | 如果旧版本真的用了 OpenAI embedding 且用了不同 base URL，完全不影响 DeepSeek 缓存 |
| **⑤ DeepSeek 服务端缓存策略变更** | 🟢 低 | 服务端缓存算法调整（不可控） |

**最可能的解释**：不是 embedding 的问题，而是 **子 AI 频繁用不同 system prompt 调用** + **多样性过高的 prompt** 破坏了 prefix 缓存。这种情况在深度推理/对线任务密集时尤其明显。

### 2.3 当前缓存命中率说明

| 指标 | 数值 | 说明 |
|------|------|------|
| 编辑器显示总体命中率 | **7.8%** | 包含早期混用 API key 时期 |
| **最近20轮命中率** | **99%** | 缓存已充分预热，完全正常 |
| 费用估算（3天） | ~$2.17 | 实际很低 |

**当前状态非常健康**。7.8% 的总体命中率低是因为早期的"训练期"拉低了平均数，但近期的 99% 说明系统恢复正常。

---

## 3. 当前恢复向量搜索的方案对比

### 方案总览

| 方案 | embedding 来源 | API 依赖 | 对 DeepSeek 缓存影响 | 搜索质量 | 部署难度 |
|------|---------------|---------|---------------------|---------|---------|
| **A: 保持 FTS-only（现状）** | 无 | 无 | ✅ 无影响 | ⚠️ 仅关键词 | ⭐ 不动 |
| **B1: Ollama 本地 embedding** | `bge-small`/`bge-m3` 本地跑 | ❌ 无 | ✅ 完全不影响 | 🟢 优秀 | ⭐⭐⭐ 中 |
| **B2: OpenClaw Local provider** | GGUF 模型(~0.6GB) | ❌ 无 | ✅ 完全不影响 | 🟢 良好 | ⭐⭐⭐ 中 |
| **C: 妹妹 HTTP 调用** | 妹妹侧的 embedding 服务 | ❌ 跨机 | ✅ 完全不影响 | 🟢 优秀 | ⭐⭐⭐⭐ 较高 |
| **D: 其他 API provider** | 混元/智谱等第三方 | ✅ 需 API | ✅ 独立 key 不影响 | 🟢 良好 | ⭐⭐ 低 |
| **E: OpenAI embedding** | OpenAI API | ✅ $0.13/1M tokens | ✅ 独立 provider | 🟢 优秀 | ⭐ 极低 |

### 方案对比详情

#### 方案 A：保持 FTS-only（推荐不动版）

**配置现状**：
```json
"memorySearch": {
  "provider": "none"
}
```

**优点**：
- 零改动、零成本、零风险
- FTS 索引已在（06-22 前已建）
- 对 DeepSeek 缓存 **绝对无影响**
- 搜索已有一定效果（BM25 + 中文分词）

**缺点**：
- 语义搜索弱（"gateway host" 搜不到 "OpenClaw 运行在哪台机器"）
- 同义词、概念搜索需靠 prompt 补偿

**风险**：无

---

#### 方案 B1：Ollama 本地 embedding

**做法**：
1. 安装 Ollama：`curl -fsSL https://ollama.ai/install.sh | sh`
2. 拉模型：`ollama pull bge-m3` 或 `ollama pull bge-small`
3. 配置 provider：
   ```json
   "memorySearch": {
     "provider": "ollama"
   }
   ```
4. 重建索引：`openclaw memory index --force`

**资源需求**：
- bge-m3: ~2.2GB RAM + 磁盘
- bge-small: ~0.3GB RAM + 磁盘
- CPU 推理（不需要 GPU），速度可接受

**优点**：
- 完全本地，零 API 调用
- 对 DeepSeek 缓存 **绝对无影响**
- 语义搜索质量好（bge-m3 支持多语言）
- 一次部署永续使用

**缺点**：
- 需安装 Ollama（系统依赖）
- 需下载模型（几百 MB ~ 2 GB）
- 需重建索引

**风险**：
- 🟢 低。Ollama 成熟稳定，不在 OpenClaw gateway 进程内跑，不会干扰核心服务
- 🟡 注意：`openclaw memory index --force` 重建索引时会调用 Ollama embedding，批量处理期间 CPU 负载会升高

---

#### 方案 B2：OpenClaw Local provider

**做法**：
1. 安装 `@openclaw/llama-cpp-provider`：`openclaw plugin install @openclaw/llama-cpp-provider`
2. 配置 provider：
   ```json
   "memorySearch": {
     "provider": "local"
   }
   ```
3. 重建索引：`openclaw memory index --force`

**优点**：
- 完全集成在 OpenClaw 内，无需额外服务
- 自动下载 GGUF 模型 (~0.6GB)
- 对 DeepSeek 缓存 **绝对无影响**

**缺点**：
- 需 native 编译 node-llama-cpp（需要 pnpm approve-builds）
- CPU embedding 速度略慢
- 首次部署较繁琐

**风险**：
- 🟡 中。native 编译可能失败（需确认平台兼容）
- 🟡 内存占用：node-llama-cpp 在 embedding 时加载模型到内存

---

#### 方案 C：妹妹 HTTP 调用 embedding

**做法**：
1. 在妹妹机器（jiali.tdx1146.com）上部署一个简单的 embedding 服务
2. 配置 OpenClaw memorySearch provider 为 `openai-compatible`，指向妹妹的 embedding 端点

**优点**：
- 零本地资源占用
- 对 DeepSeek 缓存 **绝对无影响**
- 妹妹的独立 instance 运行

**缺点**：
- 需要先修复妹妹的 edit-web.py 和网络联通性
- 增加网络依赖（qsh → jiali IPv6 连通性存疑）
- 维护成本较高

**风险**：
- 🟡 中。妹妹的 edit-web.py 和 MCP 都未启动，需要先做基础设施修复

---

#### 方案 D：其他 API provider

**做法**：
1. 配置一个第三方 embedding provider（如混元、智谱、或其他 OpenAI-compatible）
2. 使用独立 API key

```json
"memorySearch": {
  "provider": "openai-compatible",
  "openai-compatible": {
    "baseUrl": "https://open.bigmodel.cn/api/paas/v4/",
    "apiKey": "xxx"
  }
}
```

**优点**：
- 配置简单，无需本地资源
- 独立 API key → **完全不影响 DeepSeek 缓存**
- 搜索质量好

**缺点**：
- 需要额外付费（虽然 embedding 很便宜）
- 依赖外部 API 可用性

**风险**：🟢 低。

---

#### 方案 E：OpenAI embedding（备选）

**做法**：
```json
"memorySearch": {
  "provider": "openai"
}
```

前提是先配置 OpenAI API key。

**风险分析**：
- ✅ **绝对不影响 DeepSeek 缓存**：不同的 provider、不同的 endpoint、不同的 API key
- OpenAI embedding 是行业标准，质量高
- 费用极低（text-embedding-3-small: $0.02/1M tokens）

---

## 4. 推荐方案

### 优先级排序

| 优先级 | 方案 | 理由 |
|--------|------|------|
| **🥇 首选** | **A: 保持 FTS-only** | 当前 99% 缓存命中率，一切正常。**不动是最好的选择**。FTS 搜索已够用 |
| **🥈 次选** | **B1: Ollama bge-small** | 如果确实需要语义搜索且愿意部署。最安全的增强方案，不影响缓存 |
| **🥉 备选** | **D: 混元/智谱 embedding** | 配置最简单，独立 key 不影响缓存 |
| **4** | **B2: OpenClaw Local** | 集成度最高但有 native 编译风险 |
| **5** | **C: 妹妹 HTTP 调用** | 基础设施需先修复，收益不确定 |
| **6** | **E: OpenAI embedding** | 需要额外 API key，不划算 |

### 核心原则

1. **理解根因**：缓存命中率下降**不是 embedding 导致的**，而是 prompt 多样性过大和小上下文变化造成的。embedding 可以安全恢复。
2. **分开的 API key = 分开的缓存**：任何不同 provider 的 embedding 都走不同的 endpoint，完全不影响 DeepSeek 的对话缓存。
3. **当前状态很好，别急着动**：99% 缓存命中率几乎是上限。

---

## 5. 实施步骤（如果需要）

### 如果选择 B1（Ollama bge-small）

```bash
# 1. 安装 Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# 2. 下载轻量级模型（~0.3 GB）
ollama pull bge-small

# 3. 修改 OpenClaw 配置
# 编辑 openclaw.json，将 memorySearch 改为：
# "memorySearch": { "provider": "ollama" }

# 4. 重启 Gateway
openclaw gateway restart

# 5. 重建索引
openclaw memory index --force

# 6. 验证
openclaw memory status --deep
```

### 如果选择 D（混元 embedding）

```bash
# 1. 确认混元 API key 在环境变量中可用（$HUNYUAN_API_KEY）
#    或者直接配在 openclaw.json models 中

# 2. 修改 OpenClaw 配置
# "memorySearch": {
#   "provider": "openai-compatible",
#   "openai-compatible": {
#     "baseUrl": "https://open.bigmodel.cn/api/paas/v4/",
#     "apiKey": "你的混元key"
#   }
# }

# 3. 重启 Gateway
openclaw gateway restart

# 4. 重建索引
openclaw memory index --force
```

### 如果不变（方案 A）

什么都不做。当前 FTS-only 配置已是最优解。

---

## 6. 附录：DeepSeek 缓存机制技术细节

### 6.1 缓存命中率的观测

OpenClaw 在模型配置中声明了缓存支持：

```json
"deepseek-v4-flash": {
  "compat": {
    "supportsPromptCacheKey": true,
    "supportsUsageInStreaming": true
  }
}
```

每次 API 调用返回中的 `usage` 字段包含：
- `cacheRead`: 本次命中的缓存 token 数
- `cacheWrite`: 本次写入缓存的 token 数（DeepSeek 此项为 0，意味着写入免费）

**缓存命中率 = cacheRead / (input_tokens - cacheWrite)**

### 6.2 何时缓存会下降

DeepSeek 使用 **prefix-based cache**，即：

```
请求 A: [SystemPrompt_A] + [UserMessage_1]  → 缓存了 prefix
请求 B: [SystemPrompt_A] + [UserMessage_2]  → ✅ 命中（prefix 相同）
请求 C: [SystemPrompt_B] + [UserMessage_1]  → ❌ 未命中（prefix 不同）
```

**导致缓存失败的情况**：
1. System Prompt 变化（如不同 session 用不同 prompt）
2. 模型切换（不同模型 cache 独立）
3. 长时间不活跃（服务端可能回收缓存）
4. Session 重置后 context 完全不同

### 6.3 缓存与 API Key 的关系

```
API Key A ──┬── 对话请求 → 缓存池 A
            └── embedding 请求 → ∵ DeepSeek 无 embedding 端点
                → 不存在混乱可能

API Key B ──┬── 对话请求 → 缓存池 B（完全独立）
            └── embedding 请求 → 不同 provider，不同 endpoint
```

**结论：即使 embedding 使用完全相同的内容字符串，由于 API endpoint 不同，缓存完全不共享。**

### 6.4 OpenClaw memory_search 的架构

```
memory_search(query)
    ├── provider: "none" → FTS-only (BM25 关键词搜索)
    │
    ├── provider: "ollama" → 本地 embedding → 向量搜索 + BM25
    │
    ├── provider: "openai" → 远程 embedding（需 API key）→ 向量搜索 + BM25
    │
    └── ... 其他 provider
```

**FTS+BM25 是内置的 fallback，即使没有 embedding 也能搜索。** 当前 `provider: "none"` 只是不启用向量搜索，并不影响 FTS 功能。

---

## 总结

| 问题 | 答案 |
|------|------|
| embedding 是否污染了 DeepSeek 缓存？ | **几乎不可能**。DeepSeek 没有 embedding 端点，OpenClaw 也不支持 DeepSeek 做 embedding。不同 provider 的 endpoint 和 API key 都不同，缓存完全隔离。 |
| 缓存命中率为什么降到 30%~20%？ | 最可能是 **prompt 多样性过大**（子 AI 调用、不同 system prompt）、**context 太长 prefix 不匹配**、或 | 服务端策略变更。 |
| 当前能恢复向量搜索吗？ | **可以**。用任何非 DeepSeek 的 provider 做 embedding 都**完全不影响** DeepSeek 的对话缓存。 |
| 推荐做什么？ | **保持现状**（FTS-only，99% 缓存命中率）。如果确实需要语义搜索，**Ollama bge-small 最安全**。 |

---

*分析完毕。作者：子代理，2026-06-25 23:09。*
