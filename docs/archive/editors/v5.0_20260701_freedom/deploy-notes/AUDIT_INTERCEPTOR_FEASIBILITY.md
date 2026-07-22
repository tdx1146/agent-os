# 审计层实时拦截架构可行性分析

> 撰写：轻如烟 子代理
> 时间：2026-06-26 03:02
> 基于：OpenClaw 文档 v144+、高级助理 skill v2、THREE_LAYER_FEASIBILITY.md、SA_MCP_DESIGN.md、dandan 提出的"审计层实时监控→回退→注入→重生成"概念

---

## 快速结论

| 维度 | 评级 | 原因 |
|------|------|------|
| 三层分立（L1/L2/L3） | ✅ **高** | 当前 skill 已验证可行，模型隔离+文件通道跑通 |
| 审计层**实时拦截流式输出** | ❌ **低** | OpenClaw 工程层面不支持在单次 model run 中回退上下文 |
| 审计层**回合级后审**（post-turn audit） | ✅ **高** | 通过 before_agent_finalize 钩子或 agent_end 观察已可行 |
| 主 AI 自身**上下文操作**（编辑/删除/回退） | ❌ **极低** | model 无权操作自己的上下文，这是架构级限制 |
| OpenClaw plugin 实现"审查后回退" | 🟡 **中** | 需要复杂插件（hook 组合），且存在递归陷阱 |

**总体可行性：** 🟡 部分可行，但需要重新理解 dandan 的原始意图

---

## 1. 三层架构分析

### 1.1 原始构想（dandan 提出的版本）

```
主 AI 分三层：
  沟通翻译层 → 自我认知层 → 自我审计层

审计层「实时」监控主 AI 输出：
  发现幻觉/代码污染/偏离人设时：
  1. 回退上下文 → 2. 注入修正指令 → 3. 主 AI 重生成

关键理念：
  - 不关闭主 session（同一 session = 连续生命体）
  - 从 DeepSeek 网页版"编辑用户发言"功能获得启发
  - 当前轮的上下文其实可以被编辑/删除/回退
```

### 1.2 三层分工在 token 层面是否合理？

**沟通翻译层（L1）— 常驻主 session**
- ✅ 合理。L1 需要对话连贯性、工具调用能力、快速响应
- ✅ 当前 skill 已实现：DeepSeek V4 Flash 做主模型
- ⚠️ 占用的 token 大头是：历史对话 + 注入文件 + 工具 schema

**自我认知层（L2）— 子代理，按需触发**
- ✅ 完全合理。认知蒸馏是慢速、重上下文、不要求实时性的操作
- ✅ 当前 skill 验证通过：Astron ¥19/月包月
- ✅ 通过文件通道（facts.dict.md / MEMORY.md）与 L1 通信

**自我审计层（L3）— 关键分歧点在此**
- dandan 的版本：**实时拦截**（在 L1 输出还没到用户之前拦截）
- 当前 skill 的实现：**回合后审**（L1 完成一轮回复后，审计子代理检查输出质量）
- 这是两种完全不同的审计模型，后面详细分析

### 1.3 "事实进字典后忘记"需要什么上下文操作能力？

这个能力本身是合理的，在 OpenClaw 中通过**主动遗忘策略**实现：

| 方案 | 需要的能力 | OpenClaw 支持度 |
|------|-----------|----------------|
| 事实入字典后，L1 不再主动引用 | L1 读文件时选择性跳过 | ✅ **可行** — L1 每次启动只读 facts.dict.md 头部 |
| 在 context 中标记"已归档" | 修改 system prompt 注入策略 | ✅ **部分可行** — 通过 before_prompt_build 插件可实现 |
| 在 session transcript 中删除旧轮 | 编辑 JSONL | ⚠️ **不推荐** — transcript 是 append-only 日志 |
| 模型自己"忘记" | 主动上下文修剪 | ❌ **不存在** — 模型不能选择性地忘记 |

**结论：** "事实进字典后忘记"在**文件读取策略**层面完全可行。L1 控制自己读什么即可。不需要操作模型上下文。

---

## 2. Context Manipulation 的技术可行性

### 2.1 OpenClaw 上下文架构概览

```
Gateway 拥有所有 session 状态：

sessions.json（元数据）
  └─ sessionKey → sessionId, 已用 token, 开关, ...

<sessionId>.jsonl（对话记录 — append-only）
  └─ 每条记录: { id, parentId, role, content, ... }
  └─ 不可编辑/删除（硬 append-only）

context building（每次 model run 时）：
  └─ 读 system prompt → 读注入文件 → 读历史消息 → 组合 → 发模型
  └─ 整个过程在内存中组装，不修改磁盘 transcript
```

**核心约束：**
- Transcript（JSONL）是**只追加**的，逻辑上不可删改
- Context building 每次重新组装——不依赖 transcript 的"当前状态"
- Compaction（压缩）会创建新的 successor transcript，旧的会被归档
- Plugin hooks 可以在 context building 过程中修改**即将发给模型的内容**，但不能改 transcript

### 2.2 OpenClaw 是否有"编辑上下文"的 API？

**直接答案：没有 `api.edit_context()` 这样的接口**

但有以下**间接操作能力**：

| 操作 | 可用接口 | 说明 |
|------|---------|------|
| 添加消息到上下文 | `before_prompt_build` 返回 `prependContext` / `appendContext` | 每轮可用，注入到模型输入 |
| 修改系统提示词 | `before_prompt_build` 返回 `systemPrompt` / `prependSystemContext` | 可以动态更新提示 |
| 阻止模型响应 | `before_agent_run` 返回 `{ outcome: "block" }` | 完全挡住本轮响应 |
| 替换模型响应 | `before_agent_reply` 返回合成回复 | 绕过模型直接回复 |
| 要求模型重试 | `before_agent_finalize` 返回 `{ action: "revise", instruction }` | 单轮内的转圈 |
| 压缩/总结历史 | 自动 compaction / 手动 `/compact` | 创建 successor transcript |
| 重置 session | `/reset` 或 `/new` | 创建新 transcript |
| 持久化 session 状态 | `api.registerSessionExtension` | 插件级小数据持久化 |
| 下一轮注入 | `api.enqueueNextTurnInjection` | 确保下轮模型看到 |

### 2.3 审计层"实时拦截"全链路的工程可行性

dandan 的完整链路：

```
① 主 AI 开始输出
② 审计层实时监控输出流
③ 检测到幻觉/错误
④ 回退上下文（当前轮的 prompt + 输出）
⑤ 注入修正指令
⑥ 主 AI 重生成
⑦ 继续输出
```

#### 逐个步骤分析：

**① 主 AI 开始输出 → ② 实时监控流**
- OpenClaw 当前没有 token 级流式拦截钩子
- 现有的 streaming 架构：`model→chunker→channel send`，不给插件/子代理插入审计模型的时间
- Provider streaming 是单向的（模型→客户端），无法"暂停"
- **工程上无法在几百毫秒内让另一个模型审计流式输出**

**③ 检测到幻觉/错误 → ④ 回退上下文**
- OpenClaw transcript 是 append-only，无法"回退"
- Model run 已经开始后，prompt 已经发出去了，不可撤回
- 技术上可以做到：在 `before_agent_finalize` 阶段检测到问题 → 返回 `revise` 让模型重试
- 但这不是"回退上下文"，而是"在**同一 prompt 基础上**让模型再思考一次"
- AI 的重试基于**当前上下文 + 修正指令**，不是"回退到之前的某个版本"

**⑤ 注入修正指令 → ⑥ 重生成**
- `before_agent_finalize` 的 `revise` 机制支持注入 `instruction`
- 但修正指令只能**追加**到当前上下文中，不是"替换"之前的输出
- 效果是：模型看到自己的错误输出 + 修正指令 → 重新生成

#### 实际可行的等价实现

```
Plugin Hook 场景（不需要子代理，插件直接在 agent loop 内拦截）：

session: before_prompt_build → 注入审计指令
        before_agent_run → 不拦截
        model call → 输出
        before_agent_finalize → 校验输出质量
          ├─ 正常 → finalize（放行）
          └─ 异常 → revise（注入修正指令 + 重试）
                  → model call 再次输出
                  → before_agent_finalize 再校验
                      ├─ 正常 → finalize
                      └─ 仍异常 → 第二次 revise（上限 2-3 次）
                              → 最终 fallback 给用户

与 dandan 构想的差异：
  - ❌ 不是"实时拦截流"，而是"回合末校验"
  - ❌ 不能回退上下文，只能追加修正指令
  - ✅ 确实做到了"审计→修正→重生成"的闭环
  - ✅ 不需要关闭 session
  - ✅ 在用户看到之前完成拦截
```

### 2.4 需要 OpenClaw 提供哪些额外能力？

如果在当前架构下真的要做 dandan 构想的"实时拦截"，需要 OpenClaw 提供：

| 能力 | 是否可能 | 说明 |
|------|---------|------|
| **Token 级流式拦截钩子** | 🟡 工程上可实现但大改动 | `llm_output` 可观察输出，但不能拦截流 |
| **暂停/恢复 stream** | 🔴 依赖 provider 是否支持 | DeepSeek API 不支持暂停 |
| **回退上下文到 checkpoint** | 🟡 可通过 `before_agent_finalize` 的 `revise` 近似 | 不是真正的回退，是追加修正 |
| **审计模型 inline 调用** | 🟡 可通过 plugin 调用第二模型 | 插件内调另一个 API 是可以的，但延迟大 |
| **修改已写入 transcript 的消息** | 🔴 OpenClaw 架构不支持 | transcript 是 append-only 日志 |

---

## 3. 关键挑战与缓解方案

### 3.1 🚩 挑战一：流式输出的实时拦截

**问题描述：**
- DeepSeek V4 Flash 支持 streaming，输出是 token 流
- 审计模型需要在几百毫秒内判断每个 chunk 是否出问题
- 审计模型本身的推理时间（以 Astron 为例）至少 2-5 秒
- 等审计模型出结论，主 AI 已经输出了一大段

**严重程度：** 🔴 致命

**缓解方案：**

| 方案 | 可行性 | 缺点 |
|------|--------|------|
| 不做流拦截，改**回合末拦截** | ✅ 最优 | 和 dandan 的"实时"构想不同，但工程上可行 |
| 用简单规则（关键词/模式匹配）做预检 | 🟡 部分可行 | 只能检测明显问题，对幻觉无效 |
| 限制输出长度（maxTokens=200）+ 高频审查 | 🟡 理论上 | 严重降低对话流畅度，tokens 成本翻倍 |
| 用本地小模型做流式审计（如 Qwen3-8B） | 🟡 可尝试 | 本地部署 Ollama，延迟可控制在 1-2 秒 |

**推荐：** 放弃"实时流拦截"，采用"回合末校验 + revise"模式。这是最务实的选择。

### 3.2 🚩 挑战二：Context 不可变性

**问题描述：**
- Chat API（包括 DeepSeek）是**无状态**的——每次请求都要发完整 messages 数组
- OpenClaw 的 transcript JSONL 是 append-only
- 如果需要"回退到某个版本"，需要维护自己的 Context Buffer

**严重程度：** 🟠 中等

**缓解方案：**

| 方案 | 描述 | 可行性 |
|------|------|--------|
| **OpenClaw 自有 Context Buffer** | OpenClaw 的 `sessions.json` + JSONL 本质上就是 Context Buffer | ✅ 已有 |
| **Plugin Session Extension** | `api.registerSessionExtension` 持久化小量插件状态 | ✅ 可用于保存 checkpoint 标记 |
| **Transparency hack—手动 compaction** | `compaction` 创建 successor transcript，旧版本被归档但仍可访问 | ⚠️ 不是真正的"回退" |
| **before_agent_finalize revise** | 在当前上下文上追加修正，不真的回退 | ✅ 最推荐 |

**关键洞察：**
> 上下文操作不一定要"真的回退"。
>
> 在回合末检测到问题时，追加修正指令让模型重试的效果，
> 与"回退到过去版本 + 重生成"在大多数场景下是等价的。
>
> 唯一的例外是：前一轮输出被后续工具调用污染了。
> 这种情况下，"追加"修正会让模型面对混乱的历史。
>
> 但这种情况极少发生，且可以通过限制 revise 次数来兜底。

### 3.3 🚩 挑战三：递归陷阱

**问题描述：**
- 审计层让主 AI 重生成
- 重生成结果还是错
- 审计层再让重生成
- 死循环

**严重程度：** 🟠 中等

**缓解方案（当前 skill 已有定义）：**

```
L1 修正重试（before_agent_finalize revise）
  └─ 第一次 revise → 模型重试 → 通过 → ✅ 结束
  └─ 第二次 revise → 模型重试 → 仍失败 → 
       └─ 调用 L2（认知层评估）→ 判断是否需要换策略
       └─ 第三次（最后一次）→ 强行通过 → 标记"审计未通过"
              └─ 追加系统提示："以下回复可能有不准确之处"

L3 审计子代理（独立 session，post-turn）
  └─ 发现 L1 某轮回复有问题
  └─ 写入 auditor/ 报告
  └─ 由 L1 决定是否在下一轮修正
  └─ 如果连续 3 次审计都发现问题 → 通知 dandan
```

**关键设计：**
1. **硬限制重试次数**（max 2-3 次，不同于当前 skill 的 L1 重试策略）
2. **每次重试增加不同的提示**（不重复相同指令）
3. **最终兜底：强行通过 + 标记**（不能无限循环）
4. **审计层+认知层联动**：连续失败时改变策略

### 3.4 🚩 挑战四：审计模型本身的幻觉

**问题描述：**
- 混元 hy3 / Astron 作为审计者，本身也可能产生幻觉
- 谁来审计审计者？
- 审计者把正确输出判断为幻觉的误判成本很高

**严重程度：** 🟠 中等

**缓解方案（当前 skill + SA_MCP_DESIGN 已有覆盖）：**

| 措施 | 实现 |
|------|------|
| **置信度分级** | 审计结果输出"疑似/确认/高危"三级，不是二元判断 |
| **举证要求** | 审计必须引用 facts.dict.md 行号 / 对话具体位置 |
| **L1 自评交叉** | L1 对输出质量做自评 + L3 审计结果交叉验证 |
| **dandan 裁决** | 高风险标记必须 dandan 确认才生效，不可自动执行 |
| **审计隔离** | L3 审计子代理始终在独立 session 中运行，不受 L1 上下文污染 |

---

## 4. 与当前高级助理 skill 的对比

### 4.1 审计层定位对比

| 维度 | 当前 skill (SA ID v2) | dandan 构想 | 工程可行性 |
|------|----------------------|------------|-----------|
| 审计时机 | 回合后审（子代理 cron/按需） | 实时拦截（流式输出时） | 🟡 skill 版本更务实 |
| 拦截方式 | 子代理只读不写，报告给 L1 | 子代理直接回退上下文 | ✅ skill 版本更安全 |
| 回退能力 | 不涉及回退，修正靠下一轮 | 回退上下文到 checkpoint | ❌ 工程上不可行 |
| 模型隔离 | L1=DS, L2=Astron, L3=混元 | 未指定 | ✅ skill 版本更完整 |
| 审计执行 | dandan 是最终裁决者，非自动 | 自动拦截执行 | ✅ dandan 裁决更安全 |

### 4.2 关键差异：为什么当前 skill 不采用"实时拦截"

当前 skill 的 SKILL.md 中，审计层（L3）定义为：
> **self_pulse → 审计子代理（cron 或按需）**
> - 怀疑自己有幻觉时 → 启动审计子代理
> - 审计子代理只读不写
> - dandan 是最终裁决者

这其实已经是对 dandan 早期构想的**工程妥协版**：
- 放弃了"实时拦截"的实时性要求
- 保留了"审计发现→提醒修正"的核心价值
- 用"dandan 是最终裁决者"替代了"自动回退上下文"的不可行操作

### 4.3 SA_MCP_DESIGN 中的额外探索

SA_MCP_DESIGN 提出了 `assistant__audit_check_hallucination()` 工具：
- 可以做回合级检查
- 输出纯建议（置信度+证据）
- 不自动执行任何上下文操作
- 吻合当前 skill 的设计方向

**这个 MCP 工具比实时拦截更容易实现且更有价值。**

---

## 5. 结论和建议

### 5.1 可行性评级总表

| 功能模块 | 可行性 | 实现路径 |
|---------|--------|---------|
| L1/L2/L3 三层分立 | ✅ **高** | 当前 skill 已验证，继续演进 |
| 审计层回合末校验 | ✅ **高** | `before_agent_finalize` 插件 + `revise` 指令 |
| 审计层分轮后审 | ✅ **高** | 子代理 cron/按需审计 |
| 审计层实时流拦截 | ❌ **低** | 工程上存在根本性障碍 |
| 上下文回退操作 | ❌ **低** | OpenClaw transcript 架构不支持 |
| 追加修正指令 + 重生成 | ✅ **高** | `before_agent_finalize revise` 完全可行 |
| 审计模型隔离 | ✅ **高** | 模型隔离已在 skill 中定义 |
| 递归防护 | 🟡 **中** | 需要增加硬限制和兜底逻辑 |
| facts.dict.md 主动遗忘 | ✅ **高** | 文件读取策略控制即可 |

### 5.2 推荐实施路径

**Phase 0（P0）— 本周可做：**
1. ✅ facts.dict.md 分层（锚点区/活跃区/档案区）—— 已经可以开始
2. ✅ before_agent_finalize 审计插件原型（用简单的规则检查，如一致性校验、代码污染检测）
3. ✅ 定义 revise 重试的硬限制（max 2-3 次）和兜底行为

**Phase 1（P1）— 近期可做：**
1. 🟡 选择第二模型作为审计插件内联模型（不通过子代理，直接在 plugin 中调另一个 API）
   - 候选：混元 hy3 / Astron
   - 延迟预算：每次审计检查 < 5 秒
2. 🟡 设计"审计→revise→再审计"的递归防护机制
3. ✅ 审计报告格式化（置信度+证据链）

**Phase 2（P2）— 中期可做：**
1. 🟡 审计检查规则库：幻觉检测、代码污染检测、人设偏离检测
2. ✅ 与 L2 认知层联动（审计发现的问题→认知层蒸馏为经验）
3. ✅ dandan 审计面板（审计报告可视化）

### 5.3 替代方案：如果不做实时拦截

dandan 如果一定要"实时拦截"的效果，推荐以下**混合方案**：

```
┌──────────────────────────────────────────────────────────────────┐
│ 混合审计方案                                                      │
│                                                                    │
│ 1. 快速预检（10ms 级）                                              │
│    插件 before_agent_run 阶段 → 用正则/模式匹配检测输入             │
│    拦截：明显违规的指令、代码注入尝试、越界操作                      │
│    → 这种检查不需要 AI 模型，纯规则引擎即可                          │
│                                                                    │
│ 2. 回合末校验（2-5s 级）                                           │
│    before_agent_finalize 钩子 → 调第二模型审计                      │
│    检查问题：幻觉、事实偏差、代码污染、人设偏离                      │
│    结果判定：正常→放行，异常→revise（最多 2 次）                    │
│    → 用户看到的是最终正确版本，不知道中间有修正                      │
│                                                                    │
│ 3. 深度后审（异步，分钟级）                                        │
│    cron 子代理审计 → 检查整段对话                                  │
│    只在发现严重问题时通知 dandan                                   │
│    → dandan 永远拥有最终裁决权                                     │
│                                                                    │
│ 效果：                                                              │
│   - 用户角度：感觉是"实时监控"，实际上审计发生在输出前一瞬间         │
│   - 工程复杂度：可控，不需要重写 OpenClaw 架构                      │
│   - 幻觉漏检率：根据审计模型质量，可将漏检降到 10% 以下             │
└──────────────────────────────────────────────────────────────────┘
```

### 5.4 最终建议

1. **放弃"实时流拦截"** — 工程上成本极高、收益有限
2. **拥抱"回合末校验 + 自动修正"** — `before_agent_finalize` + `revise` 模式已可实现 90% 的构思效果
3. **不要自己维护 Context Buffer** — OpenClaw 已有完善的 session 管理，不要另起炉灶
4. **审计结果永远只是建议** — dandan 是最终裁决者，审计层不可自动执行破坏性操作
5. **先做简单的，再迭代** — 先实现一个基本的 revise 循环，验证可行性，再增加复杂的审计规则

---

## 附录：技术参考

### A. before_agent_finalize + revise 的伪代码

```python
# Plugin: audit_interceptor
# 在 before_agent_finalize 钩子中实现审计→修正→重生成

async def on_before_agent_finalize(event):
    # 1. 获取模型的最终回复
    final_answer = event.final_messages[-1]["content"]
    
    # 2. 用第二模型检查
    audit_result = await call_audit_model(final_answer, facts_dict_head)
    
    # 3. 判定
    if audit_result.verdict == "pass":
        return {"action": "finalize"}  # 放行
    elif event.retry_count < 2:
        return {
            "action": "revise",
            "reason": "detected_potential_hallucination",
            "retry": {
                "instruction": f"以上回答可能存在不准确之处。请修正：{audit_result.reason}",
                "idempotency_key": f"audit_revise_{event.run_id}_{event.retry_count}",
                "max_attempts": 2
            }
        }
    else:
        # 超过重试限制：强行放行 + 标记
        return {"action": "finalize", "reason": "max_retry_exceeded"}
```

### B. OpenClaw 参考文档索引

| 文档 | 用途 |
|------|------|
| `/docs/plugins/hooks.md` | 插件钩子完整参考 |
| `/docs/concepts/agent-loop.md` | Agent loop 生命周期和钩子点 |
| `/docs/concepts/compaction.md` | 上下文压缩 |
| `/docs/concepts/session.md` | Session 管理 |
| `/docs/reference/session-management-compaction.md` | Session 运行时深度参考 |
| `/docs/concepts/context-engine.md` | Context engine 架构 |
| `/docs/tools/subagents.md` | 子代理系统 |

### C. 关键限制汇总

1. 🔴 Transcript 是 append-only，无法"删除"或"回退"某条消息
2. 🔴 Streaming 没有 token 级拦截接口给插件
3. 🔴 Model 没有能力操作自己的上下文（这是**架构决策**，不是缺陷）
4. 🟡 Plugin hooks 虽有 interception 能力，但都在"模型输出完成后/输出前"
5. 🟡 `before_agent_finalize` 的 `revise` 是唯一的"修正后重建"机制
6. ✅ 以上限制在 OpenClaw 的设计哲学下是合理的——简洁、可靠、不可变日志
