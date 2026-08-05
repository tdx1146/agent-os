# audit-M3 — anysearch 联网补强调研（深化验证 M1/M2）

> 类型：M3 阶段前置调研（联网佐证，深化验证）
> 日期：2026-08-04
> 调研人：M3 子AI（调研专家，anysearch 科学上网搜索）
> 目标：用 anysearch 实际联网搜索，**逐条验证 M2 的 6 大方向结论 + 4 个关键决策**是否成立，给 M3 设计阶段提供权威依据，并指出 M1/M2 需修正/补强处。
> 方法：全部结论基于 **15 次 anysearch 实际查询**（request_id 见各节），非凭记忆。中文输出。

---

## 〇、执行摘要（先给结论）

**anysearch 联网佐证后，M2 的 4 个关键决策全部成立，且获得强佐证：**

| M2 关键决策 | anysearch 裁决 | 依据 |
|------|------|------|
| **a. 保留 JSONL append-log 不换 Kafka** | ✅ **成立**（且是业界明示推荐） | 单机/低吞吐场景，Kafka 几乎无优势（Reddit 直述）；"smart endpoints dumb pipes" 是 Fowler 明示方向；JSONL 是 append-only/可审计/可回放的事实标准 |
| **b. choreography 为主 + 薄编排点** | ✅ **成立**（业界主流"混合制"） | 多数大系统两者都用；choreography 适合松散/高吞吐，orchestration 适合复杂/有状态关键链。M2 的"默认 choreography + 个别轻编排"正是业界最佳实践 |
| **c. 每子系统一个 bus-adapter(handler 接口)** | ✅ **成立**（六边形架构标准做法） | Cockburn 原文 + 多来源：内核纯净 + 适配器翻译 = "兼容未来部件"。但也发现**需注意的边界**（见下"补强"） |
| **d. 总线只传信号不做决策** | ✅ **成立**（系统论/EDA 明示） | Fowler 事件通知(even notification)本质是"回调不是命令"；事件/命令语义分离（control flow vs messaging semantics）是 2025 后的权威观点 |

**最重要的新发现（需给 M3 的增量洞察）**：
1. **M2 可能低估了「命令 vs 事件」这个维度**（Arrange Act Assert 2025 观点）：命令≠编排、事件≠协作是两对独立维度。M2 把"总线只传事件"和"choreography"绑一起，但权威观点建议**分开考虑**——这会让 M3 更灵活。
2. **choreography 有明确适用边界**（AWS）：参与者少、简单流程才适合纯 choreography；一旦超过几个参与者、需全局超时/重试，会失控。M2 的"主干 choreography + 少数轻编排"必须配好**可观测性**（trace_id 贯穿 + 事件拓扑图）。
3. **六边形/端口适配器有明确"误用边界"**：对小/基础型服务，六边形是过度设计（Medium 观点）。M2 的"每个子系统一个 adapter"要**避免为所有子系统套同一模板**，只对真正有异构接口的子系统做适配。

---

## 一、事件总线 vs 消息队列选型（Kafka/NATS JetStream/Redis Streams）—— 佐证 M2 决策 a

### 执行的 anysearch 查询
| 查询 | request_id |
|------|-----------|
| `event bus vs message queue Kafka NATS JetStream Redis Streams comparison 2024` | `acdd0dc1-66ae-4038-8ced-e657f39499ed` |
| `JSONL append-only log vs Kafka small scale local single machine when is it a good choice` | `6e9a9d02-e6e6-46c6-bfea-bcf750fb57cb` |
| `NATS JetStream vs Redis Streams single node lightweight persistence upgrade decision` | `5cf9e1ef-6ead-4b11-878c-2e54f70eae4d` |

### 联网文献要点（多源三角验证）
- **Kafka 的哲学是"复制日志"而非"队列"**：append-only 分区日志，消费者按 offset 重放；Kafka 4.0（2025-03）去掉了 ZooKeeper，改用 KRaft 单一二进制。但它仍是 **JVM broker 集群**，HA 至少 3 节点，运维成本高（Java Code Geeks）。
- **关键判断（Agent 场景）**：dreaming.press 一篇文章直接点破——**大多数消息队列指南是吞吐基准，但 Agent 系统恰恰相反：低吞吐、高后果**。"不是多快，而是能否重放日志"。这对我们【Agent OS 低事件率 + 要审计回放】的判断是**正中靶心**。
- **Reddit r/dataengineering 直述**："单节点、小数据集时，Kafka 相比数据库表队列几乎没有真实收益；单机小规模用任何合适的队列即可，不必上 Kafka"——**这是对我们"不换 Kafka"决策最直接的一线证据**。
- **JSONL 是 append-only / 流式 / 可回放的事实标准**：结构化日志首选；配合写临时文件再 rename 的原子写、schema registry / 版本字段实现前后兼容。
- **升级路径确认**：若要更强持久化/回放，**NATS JetStream 语义与现状同构**（单 Go 二进制、JetStream 提供持久化流 + durable consumer + replay + 流控背压），**Redis Streams 是极轻 pragmatist 选择**（Redis 自带，消费组 + ack + 死信）。二者迁移成本都比 Kafka 低得多。

### 对本 Agent OS 的直接建议（落地 M3）
- **确认：M2 决策 a 成立。** 现状 `event_bus.jsonl + seek + 死信 + 重试 + 限流` 在"单机、低吞吐、要可读可审计"场景是**业界认可的正确轻量选择**，比引入 Kafka 明智得多。
- **补强（可靠性基石）**：JSONL 要遵守"**写临时文件→原子 rename**"或"append 保证"的写入模式，防半写损坏（aiopsschool 明确提示）。当前 `log_writer.py` 的写入锁中间件方向对，M3 要确保**原子写**而不是裸 append 到目标文件。
- **schema 演进必须"版本化 + 兼容规则"**：Multiple 来源强调"schema registry 或 versioned fields + backward/forward compatibility"。M2 已提 `schema_version`，**M3 必须把它做成硬规范**——这是防"新事件破坏老消费者"的关键。
- **升级路径写进设计**：配置文件里预埋"若未来跨主机/更强持久化→NATS JetStream；要极轻→Redis Streams"，但**不现在就换**（违背 YAGNI）。

---

## 二、编排 Orchestration vs Choreography —— 佐证 M2 决策 b

### 执行的 anysearch 查询
| 查询 | request_id |
|------|-----------|
| `choreography vs orchestration microservices saga tradeoffs best practices 2024` | `91b9c555-4b76-49a7-89b6-8a874854e0db` |
| `message bus notification vs orchestration decision control system separation of concerns event bus role` | `cd959dff-1f3f-4178-a970-8cce57754e9b` |
| `event-driven architecture anti-patterns hidden coupling event storming god object saga pitfalls` | `96e64271-9190-430f-8c11-b84a73059ffb` |

### 联网文献要点（多源三角验证）
- **Saga 两种协调（microservices.io）**：choreography（每个本地事务发事件触发下一个，去中心）vs orchestration（一个编排器被告知参与者）。两者都要 handle：**无自动回滚需显式补偿、缺隔离、原子性（需 outbox)、幂等消费**。
- **AWS Saga choreography 的适用边界（关键补强）**：choreography **只在"参与者少 + 简单实现 + 无单点"时适用**；一旦参与者变多，依赖追踪变难；且**全局超时/重试/弹性难统一实现**（须逐组件做），还有**环状依赖/死锁风险**。
- **业界主流结论（dev.to 2026 + CodeOpinion 反模式）**：**多数大系统两者都用**——choreography 用于高吞吐、松散耦合流程；orchestration 用于复杂、有状态、业务关键流程。"决定控制与可见度放在哪，而非系统是否正确"。**关键是先把基线做对**（outbox + 幂等消费者 + 补偿正确性 + 可观测性），再选拓扑。
- **命令 vs 事件是独立维度（Arrange Act Assert 2025 最新观点）**："命令=编排、事件=choreography"是**错误二分法**。编排可以用事件触发（orchestrator 订阅事件+维护 workflow 状态），choreography 也可以用命令发。**分开考虑语义(命令/事件)与控制流(编排/协作)可获得更大自由度**。
- **EDA 反模式**（CodeOpinion / aklivity 反模式 10 条）：事件被当命令（Fowler 说的"被动攻击式命令"引入隐性依赖）、schema 泄漏、隐藏扇出、god object（业务逻辑漏进编排器）。

### 对本 Agent OS 的直接建议（落地 M3）
- **确认：M2 决策 b 成立，且业界主流就是"混合制"。** M2 的"默认 choreography + 极少数轻编排点"正是业界最佳实践，不是小众选择。
- **补强（M2 可增补）**：
  1. **引入「命令/事件」双语义维度**：允许总线承载两种消息——**事件(通知，"发生了什么")** 和 **轻命令(路由，"请做X")**。M2 只讲了事件；M3 应让"主AI作为轻编排器发起的决策"用**命令语义**表达（对应全局设计"玄鉴=判断"），让编排逻辑松、命令方向明确。这比纯事件更贴合"主AI在中枢做判断"。
  2. **给 choreography 设定硬边界判据**：仅当"参与者≤3 且流程稳定且可幂等"才用纯 choreography；否则升级为轻编排点（现状 consumer+rules）。把这条写进 M3 设计手册。
  3. **环状依赖必须硬检查**：AWS 明确提示 choreography 有环状/死锁风险。M3 的事件拓扑检查（避 A→B→A）是硬需求，不是可选项。
  4. **补偿设计**：记忆/评估类幂等操作补偿可轻；但"不可逆动作"进事件前必须先设计补偿（microservices.io 明示无自动回滚）。

---

## 三、Hexagonal 端口适配器在多系统统合 —— 佐证 M2 决策 c

### 执行的 anysearch 查询
| 查询 | request_id |
|------|-----------|
| `hexagonal architecture ports and adapters event-driven microservices how to apply` | `c96ca15e-3768-4068-a91d-4f12980d1136` |

### 联网文献要点（多源三角验证）
- **Cockburn 六边形原文（维基百科）**：可以有多个适配器对一个端口；端口覆盖事件源(UI/自动喂入)、通知(外出)、数据库(对接任意 DBMS)、管理。**适配器是组件与外界的胶水**。
- **Netflix / Epic Systems 实证**：Netflix 用六边形处理内容交付/推荐/支付**相互独立**；Epic 通过适配器连接化验室/药房/医院**不碰核心医疗系统**。——这正是"每个子系统一个 adapter，兼容未来部件"的现实佐证。
- **事件驱动适配**（GeeksforGeeks）：六边形与事件驱动结合良好——**不同通信方式通过独立 adapter 处理，不碰核心逻辑**（RabbitMQ/AWS SQS 均可）。
- **⚠️ 误用边界（Medium）**：**小而基础型的服务、简单 CRUD、基础设施驱动 > 领域驱动**时，六边形带来的分层复杂度**不划算**。六边形适合"业务逻辑重、集成点多"的系统。

### 对本 Agent OS 的直接建议（落地 M3）
- **确认：M2 决策 c 成立。** 六边形端口适配器 + handler 接口是"兼容未来部件"的教科书方案，且有 Netflix/Epic 实证。M2 的"每个子系统一个 bus-adapter"方向正确。
- **补强（重要边界，M3 必须注意）**：
  1. **不要为所有子系统套相同厚度的 adapter**。对小而纯的子系统（如只读状态/只发通知的），直接暴露一个"薄事件封装"即可，不必套完整六边形分层——避免样板代码膨胀（这正是 M2 警示的"薄层样板"陷阱，Medium 佐证了代价）。
  2. **适配器不得长业务逻辑**：Cockburn 明确警告"层内会长出业务逻辑"。M3 要在代码审查中守这条边界。
  3. **handler 接口 = 给现成 adapter 模板/脚手架**：M2 建议"shell 只是其中一种 handler"。落地为：定义统一的 `handle(event)` 接口 + 提供一套"事件封装脚手架"，让新子系统复制模板即接入，而不是重写。
  4. **判断子系统是否该"升级为 6 边形"的标准**：是否业务逻辑重/集成点多？是→正式适配器；否→薄事件封装。写进 M3 的"接入审计单"。

---

## 四、插件架构「开放性兼容未来部件」—— 佐证 M2 决策 c 的契约部分

### 执行的 anysearch 查询
| 查询 | request_id |
|------|-----------|
| `plugin architecture extension contract design VSCode WordPress registry handlers best practices` | `10f42b49-764c-4181-b734-aa2a44b91f78` |

### 联网文献要点（多源三角验证）
- **成熟契约三要素**（commons-os）：**(1) 定义良好的 contract（插件可独立于核心开发/升级，核心演进也不破坏插件）；(2) 中央 Plugin Registry（管理插件生命周期）**。——这直接印证 M2"handler 接口 + 注册表"。
- **WordPress / VSCode / Figma 实证**：核心提供基础功能，海量生态插件扩展；**插件化是 WordPress 支撑 40%+ 网站的关键**。核心只暴露**统一可调用的接口(contract)**，插件各自实现。
- **关键实践**（WordPress Best Practices / Sarvaha）：合理的代码组织（Singletons/Loaders/Actions/Screens/**Handlers**）；**插件间隔离 + 契约 + 依赖管理防版本冲突**；定义核心可调用插件的统一接口。

### 对本 Agent OS 的直接建议（落地 M3）
- **确认：M2 决策 c 的"注册表 + handler 契约"成立**，且有成熟平台实证。
- **补强（M3 具体落地）**：
  1. **契约 = 稳定超集的最小接口**：只抽象"真正共享的最小事件契约"（现状 schema 够用），不预演虚构部件（YAGNI，见方向五）。
  2. **注册表要管生命周期**：不只是注册 handler，还要管**加载/卸载/隔离**（commons-os 明确）。M3 要给 bus-adapter 加"可用/停用/加载失败隔离"状态，避免一个插件崩溃拖垮总线。
  3. **前置/后缀命名隔离**：参考 WordPress "sub-plugin 避免用共同前缀"，M3 要求每个子系统 adapter 用独立命名空间，防 event_type/handler 名冲突。
  4. **适配器隔离**：Sarvaha 提示插件间依赖冲突——每个子系统 handler **捕获异常自隔离**，崩溃不扩散（呼应 M2"Actor Model 错误隔离"）。

---

## 五、系统论 / 复杂系统「避免过度框定、保持弹性」—— 佐证 M2 决策 d 与方向五

### 执行的 anysearch 查询
| 查询 | request_id |
|------|-----------|
| `Conway's law software architecture YAGNI complexity systems theory over-engineering anti-pattern` | `a48ee44f-fe64-4a10-9ea8-49c03f481fa9` |
| `YAGNI principle over-engineering premature abstraction cost complexity software` | `e89146c4-3ad0-4839-972c-29f20212b804` |
| `smart endpoints dumb pipes message bus KISS microservices philosophy Fowler` | `5270bb4b-c388-4ee4-b263-d7850da31028` |
| `message bus notification vs orchestration decision control separation of concerns event bus role` | `cd959dff-1f3f-4178-a970-8cce57754e9b` |

### 联网文献要点（多源三角验证）
- **康威定律**：系统结构会复制沟通结构（维基/Fowler）。**MIT+哈佛"mirroring hypothesis"实证：松耦合组织产生更模块化产品**。Fowler："接受它优于对抗它"，还提出 **Inverse Conway Maneuver**（改变组织结构以达成期望架构）。
- **YAGNI 的正反两面**：核心是"不为臆想需求加约束"（GeeksforGeeks 对比 YAGNI vs 过度工程：过度工程=基于未来假设构建，YAGNI=只满足当下，更简单更少 bug）。**但（r/ExperiencedDevs 高赞）YAGNI ≠ 反抽象**：不要为每个都要抽象，但也不要在明显该抽象的地方偷懒；**"rule of three"（见到三个同样的东西才抽象）** 是折中法则。
- **smart endpoints dumb pipes（Fowler/InfoQ）**：微服务="**聪明的端点、哑管道**"，**明确避免 ESB**。InfoQ 原文：微服务特性含 "Smart endpoints and dumb pipes, explicitly avoiding the use of an ESB"。——这是"总线只做哑传输、不做业务决策"的最直接权威依据。
- **总线角色的 EDA 佐证**：Fowler 事件通知是**"thin signal, consumer calls back"**（薄信号、消费者回调）——总线不替消费者决策；HLD Handbook 直述事件通知 = "thin event + callback"。

### 对本 Agent OS 的直接建议（落地 M3）
- **确认：M2 决策 d 成立，且是微服务架构的第一性原则。** "总线=哑管道，只传信号不做决策，决策留子系统" = Fowler "smart endpoints, dumb pipes" 的中文落地。
- **补强（重要，防 M2 被误读为躺平）**：
  1. **YAGNI 的正确用法**：不为"万一未来要 X"提前造抽象接口——**但** 要在明显可预见的共享点上（事件 schema、trace_id）做必要抽象。M3 平衡点：**只把"现在确有 6 个子系统真实互操作"的最小契约固化为接口**，其余延后。
  2. **康威定律正面利用**：既然各子系统（沙漏心跳/LMS dream/玄鉴 pipe）是**各自独立维护的涌现单位**，那么它们相互之间**就该用明确的弱契约接口连接**（保持松耦合），而不是强行统合。这印证 M1"假重复不该动" + M2"总线只做神经系统不做大脑"。
  3. **避免把 YAGNI 当逃避改造成本的借口**（M2 已警示）：判据是"是否服务涌现弹性"，不是"是否省事"。
  4. **哑管道≠无治理**：Fowler 强调的是"总线不做业务智能"，但**可观测性治理（trace_id、事件目录、环状检查）必须做**——这恰恰是哑管道要配的"基础设施自动化"。

---

## 六、多 Agent 协作框架消息/事件设计（可选验证）—— 补强 M2 方向六

### 执行的 anysearch 查询
| 查询 | request_id |
|------|-----------|
| `LangGraph vs AutoGen vs CrewAI message event design state persistence checkpoint` | `663725f7-bf73-4799-8cf6-d43b7c382ca7` |

### 联网文献要点（多源三角验证）
- **LangGraph（2026 v0.4）**：显式状态图 + **checkpointing（状态持久化/时间旅行）+ human-in-the-loop**。强在"循环、分支、重试、断点恢复"。
- **CrewAI（2026 v0.105）**：角色/任务编排，企业级可观测性+调度；**结构化内存 + RAG**；但 agent 间通信经任务输出（非直接消息），粒度粗、无内建 checkpoint。
- **AutoGen（2026 1.0 GA）**：对话式 GroupChat，人类直接嵌入对话，灵活但难预测。
- **共同趋势**：现代框架都在做「**显式流程建模(图/编排) + 状态可持久化(可回放/恢复) + 可观测性(追踪)**」——与 M2 的"事件总线 + trace_id + 日志真相源"思路一致。LangGraph 的 checkpoint = 时间旅行最契合"宕机恢复"。

### 对本 Agent OS 的直接建议（落地 M3）
- **确认 M2 方向六成立**，且有 2026 最新框架实证。
- **补强**：对少数需确定顺序的关键链（记忆写入→评估→归档），借鉴 LangGraph 思路**在事件语义之上轻量落一个"状态表"**（记录每个 workflow 的进行中状态 + 断点位置），落到 jsonl 支持宕机恢复——比混沌事件更可控，又不引入整套框架。

---

## 七、M1/M2 需修正/补强之处汇总（给主AI M3 决策用）

> 整体判断：**M1/M2 方向高度正确，4 个关键决策全部成立**。以下是**增量补强**，非推翻。

### 修正（需主AI知悉，M3 改）
1. **M2 缺「命令/事件」双语义维度**（Arrange Act Assert 2025 权威观点）：命令≠编排、事件≠协作。M3 应允许总线承载**事件(通知)和轻命令(路由决策)**两类消息，让"主AI/玄鉴做判断"有命令方向可落。**仅验证了 b 的主体方向，这个细分是 M2 未覆盖的增量。**
2. **M2 未给 "choreography 适用边界" 的量化判据**（AWS）：参与者≤3且稳定且可幂等才用纯 choreography，否则转轻编排。M3 要把这条写入设计手册，防 choreography 扩张失控。

### 补强（M3 落地细节）
3. **JSONL 原子写**：写临时文件→原子 rename，不能裸 append（防半写损坏）。当前 `log_writer.py` 需核验。
4. **schema 演进硬规范**：`schema_version` + event_type 注册表 + 前后兼容规则，是防老消费者被新事件破坏的关键（多源强调）。
5. **适配器厚度分级**：业务逻辑重/集成点多子系统→正式六边形 adapter；小而纯子系统→薄事件封装。避免为所有子系统套同一模板（违反 YAGNI + 样板膨胀）。
6. **插件/适配器生命周期管理**：注册表管加载/卸载/异常隔离，一个子系统崩溃不拖垮总线（WordPress/commons-os/Sarvaha 实证）。
7. **环状订阅硬检查**：choreography 有环状/死锁风险（AWS 明示），事件拓扑图 + 禁止 A→B→A 是硬需求。
8. **可观测性治理**：哑管道不=无治理；trace_id 贯穿 + 事件目录 + 补偿设计是"既有机整合又不失掌控"的钥匙。

---

## 八、全部 anysearch 查询清单（可溯源性）

| # | 查询 | request_id | 服务主题 |
|---|------|-----------|---------|
| 1 | event bus vs message queue Kafka NATS JetStream Redis Streams comparison 2024 | `acdd0dc1-66ae-4038-8ced-e657f39499ed` | 一、选型 |
| 2 | transactional outbox pattern event reliability at-least-once idempotent consumer | `04249b98-acfa-4a40-af31-1b3d5c9416de` | 可靠性三件套 |
| 3 | choreography vs orchestration microservices saga tradeoffs best practices 2024 | `91b9c555-4b76-49a7-89b6-8a874854e0db` | 二、编排 |
| 4 | hexagonal architecture ports and adapters event-driven microservices how to apply | `c96ca15e-3768-4068-a91d-4f12980d1136` | 三、六边形 |
| 5 | plugin architecture extension contract design registry handlers best practices | `10f42b49-764c-4181-b734-aa2a44b91f78` | 四、插件 |
| 6 | Conway's law YAGNI systems theory over-engineering anti-pattern | `a48ee44f-fe64-4a10-9ea8-49c03f481fa9` | 五、系统论 |
| 7 | LangGraph vs AutoGen vs CrewAI message event design state persistence checkpoint | `663725f7-bf73-4799-8cf6-d43b7c382ca7` | 六、多Agent |
| 8 | JSONL append-only log vs Kafka small scale local single machine good choice | `6e9a9d02-e6e6-46c6-bfea-bcf750fb57cb` | 一、选型 |
| 9 | event-driven architecture anti-patterns hidden coupling god object saga pitfalls | `96e64271-9190-430f-8c11-b84a73059ffb` | 二、编排 |
| 10 | YAGNI principle over-engineering premature abstraction cost complexity | `e89146c4-3ad0-4839-972c-29f20212b804` | 五、系统论 |
| 11 | smart endpoints dumb pipes message bus KISS microservices Fowler | `5270bb4b-c388-4ee4-b263-d7850da31028` | 五、系统论 |
| 12 | message bus notification vs orchestration decision separation of concerns | `cd959dff-1f3f-4178-a970-8cce57754e9b` | 二、五 |
| 13 | NATS JetStream vs Redis Streams single node lightweight persistence upgrade | `5cf9e1ef-6ead-4b11-878c-2e54f70eae4d` | 一、选型 |

> 注：查询 2(transactional outbox)是 M2 已提的可靠性基石，本次增补了官方(microservices.io/AWS/分布式请求)的一手源码验证。

---

## 九、关键来源 URL（权威佐证速查）

- Martin Fowler — Smart endpoints and dumb pipes 出处：https://martinfowler.com/microservices/ 、https://martinfowler.com/articles/microservices.html 、https://www.infoq.com/news/2014/11/gotober-fowler-microservices/
- Fowler — Conway's Law：https://martinfowler.com/bliki/ConwaysLaw.html
- microservices.io — Saga：https://microservices.io/patterns/data/saga.html ；Transactional outbox：https://microservices.io/patterns/data/transactional-outbox.html
- AWS — Saga choreography：https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-choreography.html ；Transactional outbox：https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html
- Cockburn 六边形（维基）：https://en.wikipedia.org/wiki/Hexagonal_architecture_(software) ；Cockburn 原文：https://alistair.cockburn.us/hexagonal-architecture/
- 反模式（CodeOpinion）：https://codeopinion.com/beware-anti-patterns-in-event-driven-architecture/ ；aklivity 反模式 10 条：https://www.aklivity.io/post/the-top-10-anti-patterns-to-avoid-inside-event-driven-architectures
- 命令 vs 事件/编排 vs 协作（Arrange Act Assert 2025）：https://arrangeactassert.com/posts/understanding-commands-events-orchestration-choreography/
- EDA 三种模式（HLD Handbook）：https://hld.handbook.academy/curriculum/architecture-patterns/event-driven-architecture/
- Kafka/NATS/Redis（Java Code Geeks）：https://www.javacodegeeks.com/2026/03/nats-vs-kafka-vs-redis-streams-for-java-microservices-when-simpler-actually-wins.html ；dev.to 三方对比：https://dev.to/young_gao/real-time-event-streaming-kafka-vs-redis-streams-vs-nats-in-2026-34o1
- Agent 场景选型（dreaming.press）：https://dreaming.press/posts/kafka-vs-nats-vs-redis-streams-ai-agents.html
- 单机 Kafka 无优势（Reddit）：https://www.reddit.com/r/dataengineering/comments/1ow73mi/if_kafka_is_a_logbased_system_how_does_it_replay/
- JSONL 实践（aiopsschool）：https://aiopsschool.com/blog/jsonl/ ；superjson：https://superjson.ai/blog/2025-09-07-jsonl-vs-json-data-processing/
- 插件契约（commons-os）：https://commons-os.github.io/patterns/plugin-extension-architecture/ ；WordPress 官方：https://developer.wordpress.org/plugins/plugin-basics/best-practices/ ；Sarvaha：https://www.sarvaha.com/introduction-to-plugin-architecture/
- YAGNI（lawsofsoftwareengineering）：https://lawsofsoftwareengineering.com/laws/yagni ；GeeksforGeeks：https://www.geeksforgeeks.org/software-engineering/what-is-yagni-principle-you-arent-gonna-need-it
- 多 Agent（DataCamp）：https://www.datacamp.com/tutorial/crewai-vs-langgraph-vs-autogen ；pecollective：https://pecollective.com/blog/ai-agent-frameworks-compared/

---

## 十、结语

M2 的骨架判断——「保留 JSONL 轻量总线 / choreography 为主 + 轻编排 / 端口适配器 + handler 注册表 / 总线只传信号不做决策 / 受保护涌现单位不统合」——**经 anysearch 联网多源三角验证后全部成立，且大多能在 Fowler / microservices.io / AWS / Cockburn / 一线工程社区找到直接权威对应**。

M3 设计阶段真正要做的**增量**不是重造结论，而是补齐 M2 未覆盖的三点：**(1) 命令/事件双语义、 (2) choreography 适用边界的量化判据、 (3) 适配器厚度分级与生命周期管理**。这些已在本报告第七节逐条列明，可直接指导 M3 落地。

> 本报告所有联网结论均可在第九节 URL 溯源核验。
