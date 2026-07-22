# 高级助理 MCP 工具 — 初步设计蓝图

> **状态**: 设计愿景 · 未实现  
> **日期**: 2026-06-25  
> **背景**: 三层架构（沟通翻译层/自我认知层/自我审计层）从静态 skill 升级为真正的 MCP 工具框架  
> **动机**: skill 不稳定（dandan 指出），MCP 工具具有更强的稳定性和可组合性

---

## 架构概览

```
┌──────────────────────────────────────────────────────────┐
│                    主 AI 会话（沟通翻译层）                 │
│  日常对话、自然语言理解、工具调度、回应生成                 │
│  → 不需要 MCP 工具：这是主 AI 本身的能力                   │
└──────────────────────┬───────────────────────────────────┘
                       │ 调用 MCP 工具
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ 认知层   │ │ 审计层   │ │ 翻译层   │
   │ MCP工具  │ │ MCP工具  │ │ (无工具) │
   └──────────┘ └──────────┘ └──────────┘
```

### 核心原则

1. **沟通翻译层不需要 MCP 工具** — 沟通翻译层本身就是主 AI 的日常对话能力，不需要额外工具化
2. **MCP 工具只服务于认知层和审计层** — 这两个层次对持久化、结构化、可审计性有特殊需求
3. **每个 MCP tool 只做一件事** — 单一职责，接口清晰，便于组合
4. **审计层只读不写** — 审计工具的输出不能影响主 session 的上下文或状态
5. **认知层读写 facts.dict.md** — 不干扰 sandglass 沙漏系统的工作

---

## MCP 工具清单

### 一、自我认知层（Self-Cognition Layer）

认知层负责 agent 对自身和环境的持久化知识管理。它和 sandglass 的关系是互补的：
- **sandglass** 负责 episodic memory（事件序列、过程日志）
- **认知层 facts.dict.md** 负责 semantic memory（事实、规则、偏好、结论）

#### `assistant__cognition_save(topic, content, type)`

**用途**: 保存一条认知到 facts.dict.md

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `topic` | string | 认知主题，如 "dandan-tts-preference"、"debug-pattern-python-path" |
| `content` | string | 认知内容 |
| `type` | string | 可选：`assertion`（断言）、`preference`（偏好）、`rule`（规则）、`lesson`（教训）、`pattern`（模式） |

**行为**:
1. 检查 topic 在 facts.dict.md 中是否已存在
2. 存在则更新（追加时间戳版本），不存在则新建条目
3. 写入格式保持 facts.dict.md 的结构一致
4. 返回 `{status: "ok", fact_id: "..."}`

**示例**:
```
assistant__cognition_save(
  topic="dandan-tts-preference",
  content="dandan 明确表示 TTS 用 edge-tts，理由是 ElevenLabs 延迟高",
  type="preference"
)
```

#### `assistant__cognition_query(topic)`

**用途**: 按主题查询已保存的认知

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `topic` | string | 认知主题，支持前缀匹配 / 模糊匹配 |
| `limit` | int | 可选，返回最多条数，默认 5 |

**行为**:
1. 在 facts.dict.md 中搜索匹配 topic 的条目
2. 支持精确匹配和前缀匹配
3. 如果 topic 为空或 `*`，则返回最近 N 条认知
4. 返回结果按时间倒序排列

**返回**:
```json
{
  "results": [
    {"topic": "dandan-tts-preference", "content": "...", "type": "preference", "updated_at": "2026-06-25T12:00:00"},
  ]
}
```

#### `assistant__cognition_list(pattern)`

**用途**: 列出所有认知主题（或匹配某模式的主题）

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `pattern` | string | 可选，按 glob 模式过滤 |
| `type` | string | 可选，按 type 过滤 |
| `limit` | int | 可选，默认 50 |

**返回**: 主题列表 + 各主题的 summary（最近一次更新的时间和内容摘要）

#### 存储设计

**文件**: `facts.dict.md`（已有文件，格式扩展）

**格式扩展建议**:
```markdown
## dandan-tts-preference  [type:preference]
- dandan 明确表示 TTS 用 edge-tts，理由是 ElevenLabs 延迟高
- 记录时间: 2026-06-25 12:00:00
- 来源: conversation_20260625_001

## debug-pattern-python-path  [type:lesson]
- 虚拟环境的 Python 路径必须用 `which python` 确认，不要假设
- 记录时间: 2026-06-24 14:30:00
- 来源: conversation_20260624_003
```

**为什么不直接用 sandglass 搜索？**
- sandglass 擅长事件序列搜索（"发生了什么"）
- facts.dict.md 擅长事实查询（"事实是什么"）
- 两者互补，认知层工具封装了对 facts.dict.md 的 CRUD

---

### 二、自我审计层（Self-Audit Layer）

审计层负责对 agent 自身状态的监控和诊断。**审计工具的输出对主 session 不可写**，确保审计不会意外破坏对话状态。

#### `assistant__audit_check_context()`

**用途**: 检查当前上下文的状态指标

**返回**:
```json
{
  "context_length": 45231,
  "context_limit": 64000,
  "usage_pct": 70.7,
  "tool_calls_this_turn": 8,
  "tool_calls_limit": 50,
  "over_limit": false,
  "warnings": [
    "上下文已使用 70%，建议考虑压缩",
    "本回合工具调用 8 次"
  ]
}
```

**行为**:
- 纯读取主 session 的上下文元数据
- 不修改任何现有内容
- 不向主 session 写入任何内容

#### `assistant__audit_check_hallucination()`

**用途**: 检查最近输出的文本是否有事实性错误

**方法**: 通过交叉验证、自洽性检查来检测可能的幻觉

**返回**:
```json
{
  "checks_performed": 3,
  "suspicious_statements": [
    {
      "statement": "xxx",
      "reason": "与 facts.dict.md 中的记录矛盾",
      "confidence": 0.85
    }
  ],
  "verdict": "pass" | "flag" | "fail"
}
```

**行为**:
- 对比最近输出与 facts.dict.md / sandglass 中的已知事实
- 标记矛盾、未经证实的陈述
- 不修改主 session 输出

#### `assistant__audit_compress(target, strategy)`

**用途**: 压缩或清除指定范围的上下文（需要审计后执行的操作）

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `target` | string | `"full_history"` / `"tool_results"` / `"last_N_messages"` |
| `strategy` | string | `"summarize"`（摘要压缩）/ `"drop"`（丢弃系统消息以外的内容）/ `"keep_keys"`（保留关键信息丢弃细节） |

**返回**:
```json
{
  "original_tokens": 52000,
  "compressed_tokens": 18000,
  "savings_pct": 65.4,
  "status": "ok"
}
```

**安全约束**:
- 不能压缩系统提示词（system prompt）
- 不能压缩最近的 2 轮对话（保证对话连贯）
- 不能压缩待办清单中的活跃条目

---

## 与现有系统的关系

| 组件 | 关系 | 备注 |
|------|------|------|
| **Sandglass 沙漏** | 互补 | 沙漏做事件序列（episodic memory），认知层做事实存储（semantic memory） |
| **facts.dict.md** | 认知层存储后端 | 认知层工具封装 facts.dict.md 的读写 |
| **SOUL.md / persona.md** | 认知数据的源头之一 | 认知层可以从这些文件导入种子数据 |
| **memory/ 目录** | 不受影响 | 认知层不读写 memory/*，避免冲突 |
| **self_pulse 自主回路** | 可调用审计工具 | self_pulse 可定期调用 audit_check_context 判断是否需要压缩 |
| **backlog.md 待办清单** | 不受影响 | 审计层只检查上下文指标和输出质量 |

---

## 风险与注意事项

1. **审计层只读原则不可违背** — 如果有写需求，必须由主 AI 主动调用，审计工具不能自动修改上下文
2. **facts.dict.md 并发安全** — 多子 agent 同时写 facts.dict.md 需要锁机制或原子写入
3. **审计层的额外成本** — 每次审计检查都会消耗 tokens，需控制审计频率
4. **不要把认知层做成第二个 sandglass** — 认知层存事实，sandglass 存事件，不要混淆
5. **工具前缀 `assistant__`** — 保持与现有 sandglass MCP 工具的前缀风格一致

---

## 后续步骤（不在本蓝图中实现）

1. 确定 MCP 工具的部署框架（OpenClaw 原生 MCP 还是自定义 HTTP server）
2. 确定工具注册方式（openclaw.json 还是其他配置）
3. 设计 facts.dict.md 的存储格式正式规范
4. 实现原型并走通端到端
5. 压测并发读写安全性

---

*蓝图初稿 · 2026-06-25 · 集成 dandan 讨论意见*
