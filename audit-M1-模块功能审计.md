# audit-M1 — 本地模块功能审计

> 类型：M1 审计报告（系统架构 / 系统论视角）
> 日期：2026-08-04
> 审计人：M1 子AI（系统架构审计专家）
> 目标：从系统论「有机整合 + 开放弹性 + 兼容未来」视角，逐一深读本地模块，回答**功能重复 / 过度框定/弹性 / 可整合性**，并给出「真重复 / 假重复 / 真缺口」的系统论结论。
> 状态：**本报告已落盘**（本轮强制成文）。

---

## 〇、摘要（先给结论）

一句话：**Agent OS 的骨干方向是对的，但「事件总线」被复制成了一个失控的双胞胎 + 一条断头路；「胶水层」是唯一架构正确的端口适配层，却处于断电待机状态。**

- **事件总线碎片化（坐实，比预想更严重）**：存在 **4 个物理 `event_bus.jsonl`** + **2 套各自演化的 event bus 代码**。真正被消费的只有 iso-sand 那一套；丰碑自己的 `xuanjian_pipe` 写入的 `丰碑/code/data/event_bus.jsonl` **没有任何消费者**（断头路）；`monument_bridge` 写入的 `丰碑/data/event_bus.jsonl` 是空文件、同样没人读。
- **前位审计员的 3 条线索**：① 碎片化 ✅ 坐实（且更复杂）；② iso-sand consumer「不在 ps」**❌ 有误**（PID 1641746 确实在跑，见第五节）；③ 胶水层只被 examples/score_examples.py 引用 ❌ **有误**——实际被 `glue_server.py` 完整引用，但该服务**未启动运行**（见第四节）。
- **调度/心跳/事件三类功能高度重叠**，散布在 iso-sand、丰碑、verify_daemon、沙漏、LMS 五个位置，但**大多是"内部自维护闭环"，不是该统合的重复**。
- **真缺口（该缝）**：① 总线 `producer→event→consumer` 接入协议不统一、未对所有子系统铺开；② xuanjian_pipe 这个最重要的生产者把事件写进了死胡同；③ 胶水层（记忆编排）与事件总线（调度/信号）**两套骨架并存但互不相连**。
- **假重复（该护）**：沙漏 heartbeat/nightwatch、LMS dream_engine 的做梦与自维护、verify_daemon 的文件变更校验，全部是子系统**内部**自维护闭环，统合它们会破坏内聚（跨系统论断：康威定律反面 + 负反馈自组织章节）。

---

## 一、审计范围与证据地图（读过的每份关键文件）

| 模块 | 位置 | 状态 |
|------|------|------|
| iso-sand 事件总线 | `/vol2/1000/AI专用/Agent OS/iso-sand/` | 运行中（调度+消费者） |
| 丰碑 event_bus（分叉） | `/vol2/1000/AI专用/丰碑网络/code/event_bus/` | 未启动（代码分叉） |
| 丰碑 xuanjian_pipe | `/vol2/1000/AI专用/丰碑网络/code/core/xuanjian_pipe.py` | 写入断头总线 |
| 丰碑 audit/archive | `/vol2/1000/AI专用/丰碑网络/code/core/` | 被 iso-sand 规则调用 |
| 丰碑 monument_bridge | `/vol2/1000/AI专用/丰碑网络/code/integration/monument_bridge.py` | 含 Windows 路径 |
| 胶水层 interfaces | `/vol1/@apphome/trim.openclaw/data/workspace/interfaces/` | 未启动（待机） |
| 胶水层 HTTP 入口 | `/vol1/@apphome/trim.openclaw/data/workspace/glue_server.py` | 未启动 |
| 沙漏 sandglass_source | `/vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source/` | 正常（自维护） |
| 活体记忆 LMS | `/vol2/1000/AI专用/living-memory-system-cloud/` | 正常（自维护） |
| 玄鉴/同构沙盘 verify_daemon | `/vol2/1000/AI专用/AgentOS-IsoSand/同构沙盘/src/verify_daemon.py` | 运行中（PID 3183279） |

---

## 二、模块逐一审计

### 模块 1：iso-sand 事件总线（调度器 + 消费者）

**职责**：以 `event_bus.jsonl`（append-log）+ `event_bus.seek`（offset）+ 死信 + 重试 + 限流构成轻量事件队列；`task_scheduler.py` 按 cron 定时执行任务并写事件；`event_consumer.py` 轮询事件、用 `event_rules.yaml` 规则把事件分派为下游动作。

**关键证据**：
- 运行中：
  - PID 1641741 = `python3 .../.run_scheduler.py`（Jul22 起，累计 0:46 CPU）
  - PID 1641746 = `python3 .../.run_consumer.py`（Jul22 起，累计 3:28 CPU）
  - 二者不是"没起"，是从 7-22 挂到现在（跨约 13 天）。这推翻了线索②。
- `deploy/event_schema.yaml`（43行等效）：`event_types` = task_complete / anomaly / audit_result / milestone / consumer_action；`required` = t/event_type/producer/result；`optional` = trace_id/detail/payload。
- `deploy/event_rules.yaml`（v0.4.1，43行）：规则用 **`command:` shell 字符串插值**（`{trace_id}`），3 条规则全指向丰碑（audit.py / alerts.log / archive.py）。
- `task_scheduler.py` L161-171 用 `subprocess.run(command, shell=True)` 执行任务；`load_tasks([])` 在 `.run_scheduler.py` 里传了空列表 → **当前调度器实际没排任何 cron 任务**（`tasks=[]`），它现在只是空转 tick。真正的丰碑任务配置在 `丰碑/code/event_bus/tasks.yaml`（health_check 每10min / db_maintenance 每天3点 / freeze_check 每6h / periodic_sync 每30min），但那套 fork **没在跑**。

**重复**：与丰碑 fork 是同源双胞胎（见模块5）；与 verify_daemon 都做「监控日志→动作」但目标不同（事件 vs 文件变更）；调度功能与 LMS 的 dream_scheduler、沙漏 heartbeat 重叠（见第六节论断）。

**弹性（过度框定）**：
- ⚠️ `deploy/event_rules.yaml` 的 `command:` 用**字符串插值拼 shell**（L17/29/41），存在注入面；且新下游必须改文件 + 重启 → **开放性不足**（M2 报告的"症结"在此坐实）。
- ⚠️ `_DEFAULT_RULES_FILE` 在 src/event_consumer.py L29 指向 `src/event_rules.yaml`，但实际规则在 `deploy/event_rules.yaml`（靠 .run_consumer.py 显式传参才用对）→ **双份规则文件 + 隐式路径错配**，易踩坑。
- ⚠️ 硬编码绝对路径在起停脚本（start_all.sh / rule 内 丰碑路径）里，换机/迁移必须全改。
- ✅ 好在：schema 有 `payload: object` 自由扩展、`trace_id` 串联，已具备"最小契约不锁死新类型"的好底子。

**可整合性（接入全局总线代价）**：**代价极低，因为它本身已是总线**。它当前唯一缺陷是：① 消费者用 shell 动作（升级为 handler 接口即开闭）；② 规则文件双份（统一到一处）；③ 尚无 producer 生态（只有自己调度器写事件）。它是"总线骨架"，只要把各子系统以 adapter 形态接到它（producer 发布 + handler 订阅），就完成统合，几乎不改内核。

---

### 模块 2：胶水层 interfaces（integration_service + adapters）

**职责**：Hexagonal「端口+适配器」记忆编排层——`SensorPort`（向量）+ `CognitivePort`（沙漏/LMS）+ `ApplicationPort`（丰碑）三端口，`IntegratedMemoryService` 提供 `store`（聚合写入）/ `recall`（协同检索）/ `contribute`（知识贡献）/ `get_status`（状态聚合）。`glue_server.py` 是它的 HTTP 入口（port 19000）。

**关键证据**：
- `interfaces/services/integration_service.py` 是**架构上最干净的一个模块**：只依赖注入的抽象 Port，不含任何具体后端 import（L25 注释"本类不 import 具体适配器"）；`recall` 用可覆盖权重 text0.3/vector0.5/lms0.2 融合。
- `interfaces/base.py` 定义 SensorPort/CognitivePort/ApplicationPort + 各自 Dummy 降级实现（L29-215）——**完美的"Dummy 降级=可替换后端"弹性**（Cockburn 端口语义）。
- 引用关系（grep 坐实）：只有 `glue_server.py` + `tests/` 引用 `interfaces`。`examples/score_examples.py` 也存在。**没有任何 OpenClaw 运行时 / 插件 import 它**。
- **`glue_server.py` 未运行**（`ps` 无进程）→ 整个胶水层**当前是"断电待机"**。

**重复**：与 MongoDB/向量直连调用重复？未见——它反而是**收口**现有分散调用的正确层。但与事件总线（模块1）关系是**两套骨架并存、互不相连**：总线管"调度/信号"，胶水管"记忆编排"。

**弹性（过度框定）**：
- ⚠️ `glue_server.py` L29 `LMS_URL=...8190`、L34 `VECTOR_URL=http://192.168.0.103:11435/...` → **硬编码了向量服务的内网 IP**（192.168.0.103），跨机/换环境会断。
- ✅ 其余部分（Dummy 降级、Port 抽象、权重可覆盖）是**教科书式不过度框定**，为当前已验证需求设计，符合 YAGNI。

**可整合性（接入总线代价）**：**这是最值得接入总线的模块——而且是"答案"级的适配器层**。它已经具备 Hexagonal「port+adapter」，新子系统只需实现一个 port 适配器即可进胶水层；若把胶水层的 `store/recall/contribute` 作为总线的 **handler 接口实现**（而非现在的 shell 命令），就能实现 M2 借鉴②「把 shell 动作升级为 handler 接口」。代价：启动 glue_server + 为总线加一个 producer(胶水层发记忆事件) + 一个 handler(总线事件→胶水动作)。**收益最大，代价最低，是 M3 设计的 C 位**。

---

### 模块 3：沙漏 sandglass_source（heartbeat / nightwatch / pulse / l3_tasks）

**职责**：显式叙事记忆（`sandglass.txt` 明文权威源）。四个被审文件是沙漏的**内部自维护层**：
- `heartbeat.py`：每 10 分钟健康检查 + 环境感知（Windows/Mac/Linux 跨平台 ps），写 `heartbeat.log`。
- `nightwatch.py`：会话启动时 3 层健康守卫——**自愈**（末行损坏自动切除、主沙漏被截断自动从 `sandglass.backup` 恢复、compaction 告警）。
- `pulse.py`：对话前深度感知（体验/情绪/环境），自动中英切换。
- `l3_tasks.py`：跨会话承诺追踪（task_defer/pending/done/trigger）。

**关键证据**：
- `heartbeat.py` L3-5：零依赖跨平台（tasklist/ps -ax/ps -aux）——**刻意不依赖任何基础设施**。
- `nightwatch.py` L17-22：`_sealed` 封框完整性校验；L38-53 阴影副本恢复机制——**纯内部自愈**。
- `pulse.py` L67-69、`l3_tasks.py` L21-22：都指向 `sandglass_paths._NB`（沙漏 vault 目录）。

**重复**：与 iso-sand 调度器「周期性 tick」、与 event_bus 「health/anomaly」**表面上重复**（都在做"周期检查/健康/状态"）。但对系统论而言这是**假重复（该护）**——它是沙漏自己的心跳与自愈，不依赖任何外部总线；统合它 = 把沙漏的命根子外包，破坏内聚。

**弹性（过度框定）**：**几乎没有过度框定，是全系统最"有机"的例子**——零依赖、自愈、跨平台、可缺件降级。唯一小点：`nightwatch._sealed` 硬编码了 5 个文件名的存在校验（`nightwatch.py` L17-22），属"内聚自我保护"而非框定。

**可整合性**：**不建议接入总线**（这是"该护"的假重复）。若要"观测性"缝合，只需让沙漏**只发事件通知**（存活/告警）给总线、不改变其内核；总线只做观测不做决策。代价最低（加一个 producer），但**不是必须**。

---

### 模块 4：活体记忆 LMS（dream_engine / memory / dream_scheduler）

**职责**：隐式塑形记忆（Attractor 网络 + J 矩阵）。`dream_engine.py` 七阶段做梦周期（NREM 巩固/SHY 下调/遗忘修剪/景观漂移/目的演化/REM 整合/快照）；`dream_scheduler.py` 常驻线程监控会话空闲、超阈值自动做梦、对话时暂停。

**关键证据**：
- `dream_engine.py` L1-24：NREM 回放巩固 + SHY 突触下调 + FEP/主动推断，理论支撑扎实——纯**内部记忆运算**。
- `runtime/dream_scheduler.py` L4-12：后台守护线程监听会话空闲、`idle_threshold=30s` 触发做梦、对话优先暂定。这是 LMS **内部**的空闲态自调度。

**重复**：`dream_scheduler` 与 iso-sand `task_scheduler` **都叫"调度器"且都常驻**，但**语义完全不同**：一个非调度 cron 任务（执行 shell），一个在调度"记忆做梦"（内存运算）。这是**同名异构实体的假重复**——合并会毁掉二者的语义边界（跨系统论断：命名混淆 ≠ 功能重复，见第六节）。

**弹性（过度框定）**：`dream_engine.py` L29-43 `_SNAPSHOT_VERSION="0.3.0"` 故意**硬编码**以避免 core 反向依赖 persistence 层（保持 DAG 无环）——**这是有意的架构约束，不是框定**。未发现过度框定。`dream_scheduler.py` 的 `idle_threshold=30`、`check_interval=5` 为可选参数，可调。

**可整合性**：**不建议接入总线**（该护）。LMS 的做梦是它内部的自组织运算（对应沙漏 heartbeat 同理）。若要观测，可让它**发一个 `dream_complete` 通知事件**给总线，仅作为可观测性信号，不改内核。

---

### 模块 5：丰碑（xuanjian_pipe / audit / archive + 隐藏的 fork）

**职责（三层）**：
- `xuanjian_pipe.py`：玄鉴评分管道——接收入站洞察，三轴判别（time_binding/transferability/abstraction），触发候选/积分。
- `audit.py` / `archive.py`：事件总线规则的**下游动作**（被 iso-sand consumer 的 rule-task-complete 触发，接收 trace_id 做丰碑审计/归档）。
- **`丰碑/code/event_bus/` 是 iso-sand 事件总线的完整分叉副本**（task_scheduler.py 10814B / event_consumer.py 19634B / log_writer.py 8148B / event_rules.yaml 237 行 / tasks.yaml 完整任务配置）。

**关键证据（线索④ + 新增）**：
- `xuanjian_pipe.py` L113：`LogWriter(filepath=.../丰碑/code/data/event_bus.jsonl)` → **它写进 `丰碑/code/data/event_bus.jsonl`**（该文件现有 4 条 WARN 事件，时间戳 08-04）。但 **没有任何消费者读这个路径**（grep 全仓库无消费 `code/data/event_bus` 的代码）→ **断头路**。
- `monument_bridge.py` L40：`_ISOSAND_BASE = r"Z:\QH\AI专用\Agent OS\iso-sand"` → **Windows 路径硬编码**（线索④坐实），且它定义的 `EVENT_BUS_PATH = 丰碑/data/event_bus.jsonl`（该文件 0 字节、无消费者）→ 又一条断头。
- **fork 分歧**：iso-sand `deploy/event_rules.yaml`（v0.4.1，43行）用 `command:` shell 字符串插值（有注入面）；丰碑 `event_bus/event_rules.yaml`（v0.6.0，237行）已升级为 **`exec: python` + `script:` + `EVENT_DATA` 环境变量**（消除注入风险，安全加固）——**两套规则 schema 已分叉**。但**在跑的是旧的 iso-sand v0.4.1**，安全加固版没在跑。
- `丰碑/code/event_bus/data -> /vol2/1000/AI专用/Agent OS/iso-sand/data`（**symlink**）——fork 试图"借用" iso-sand 的数据目录，但 event_bus.jsonl 实际物理文件各自独立。
- 丰碑 git 有提交历史（`e173c5a` health_check 对齐 / `638953f` Windows compat / `89e6c29` 初始同步）→ fork 在 git 里独立演进。

**重复（真重复！）**：`丰碑/code/event_bus/` 是 **iso-sand 事件总线的完整重复实现**，且已演进到不同版本。它本该是"接入客户端/适配器"，却复制了整条总线。**这是本审计发现的头号真重复**——同一个总线逻辑被维护了两份，schema 已分叉（v0.4.1 vs v0.6.0），一旦同时跑会双写/抢 seek。

**弹性（过度框定）**：`xuanjian_pipe.py` 只认 `丰碑/code/data/event_bus.jsonl`（硬编码相对路径，靠 `os.path.dirname(__file__)`，若位移即断）；`monument_bridge.py` L40 Windows 硬编码（跨机器碎片化坐实）。

**可整合性**：**必须治理**。xuanjian_pipe 是最重要的知识生产者，它的事件必须进**被消费的主总线**（iso-sand/data/event_bus.jsonl），而非死胡同 `code/data/`。治理方向：① 三处 `event_bus.jsonl`（iso-sand、code/data、丰碑/data）归并为**一个统一总线文件**（或一个可配置总线地址）；② 让 xuanjian_pipe / monument_bridge 把事件发布到统一总线；③ **砍掉或冻结 `丰碑/code/event_bus/` 这个 fork**（不双维护），保留其安全加固思路（exec+script）移植回主消费者。代价：中（管代码归属 + 统一 producer 路径）。

---

### 模块 6：玄鉴/同构沙盘 verify_daemon

**职责**：独立守护进程（`同构沙盘/src/verify_daemon.py`，PID 3183279），监控 `同构沙盘/data/operation_log.jsonl` 新条目，对文件变更条目做关键词重叠校验，结果写 `daemon_audit.log`。核心是"文件变更 → 校验是否忠实执行"的**玄鉴内核校验**。

**关键证据**：
- verify_daemon.py L42-44：`LOG_PATH = 同构沙盘/data/operation_log.jsonl`、`AUDIT_PATH = data/daemon_audit.log`、`SEEK_PATH = data/daemon.seek`——**自带 seek 游标**（又一个消费者语义）。
- 它读的 `同构沙盘/data/operation_log.jsonl`（26529B，07-16 更新）与 iso-sand 的 `data/operation_log.jsonl`（446B，07-22 更新）**是不同文件、不同历史** → 又一个异构的"operation_log"。
- 运行中：`ps` 显示 `3183279 .venv_daemon/bin/python src/verify_daemon.py`（Aug01 起，0:03 CPU）。

**重复**：与 event_consumer **都在"监控一个 log + 带 seek + 写审计"**（都是消费者模式），但**语义不同**：event_consumer 消费"事件总线"，verify_daemon 消费"文件变更日志做玄鉴校验"。这是**同构模式（消费者 + offset）在不同域的复用**——反映"消费者模式"是通用骨架，但**不该合并**（两域目标不同，合并会互相干扰 seek 与规则）。

**弹性（过度框定）**：
- ⚠️ verify_daemon.py L44-49：`KERNEL_SPEC_DIR = Path("/vol2/1000/AI专用/AgentOS-IsoSand/内核层规范")`（**硬编码绝对路径**）；`PROJECT_ROOT = Path.cwd()`（**依赖 cwd 启动**，若从别处启动会跑偏，虽有兜底但仍脆弱）。
- ⚠️ L42：假定 `LOG_PATH = PROJECT_ROOT/data/operation_log.jsonl`，若 operation_log 物理位置迁移即断链。

**可整合性**：**不建议接入总线内核**（该护——它是玄鉴自己的校验闭环）。但它的"文件变更校验"结果天然是**好事件来源**（可发 `audit_result` 事件通知给总线）。vever daemon 的 seek 机制可作为「消费者+offset」模式的**第三条参照**，印证总线的通用性，而非与其合并。

---

## 三、核心证据汇总表（文件 + 行号）

| 结论 | 证据（文件:行号） |
|------|-------------------|
| 总线骨架在跑（调度+消费者） | PID 1641741 (scheduler) / 1641746 (consumer) |
| 调度器任务列表为空（空转） | iso-sand/.run_scheduler.py: `s.load_tasks([])` |
| 规则文件双份、消费者默认指向错位 | iso-sand/src/event_consumer.py:28-29 `_DEFAULT_RULES_FILE` |
| 旧规则用 shell 字符串插值（注入面） | iso-sand/deploy/event_rules.yaml:17,29,41 `command:` |
| fork 已升级安全加固但没在跑 | 丰碑/code/event_bus/event_rules.yaml v0.6.0 `exec+script` |
| fork 与 iso-sand 分叉 | diff 两 event_consumer.py 整体不同; rules 43 vs 237 行 |
| fork 借用 iso-sand 数据目录 | 丰碑/code/event_bus/data -> iso-sand/data (symlink) |
| xuanjian_pipe 写死胡同总线 | xuanjian_pipe.py:113 `.../丰碑/code/data/event_bus.jsonl` |
| monument_bridge Windows 路径 | monument_bridge.py:40 `r"Z:\QH\AI专用\Agent OS\iso-sand"` |
| monument_bridge 写另一个空总线 | monument_bridge.py:54-56 `EVENT_BUS_PATH=丰碑/data/event_bus.jsonl`(0B) |
| 胶水层 4 物理 event_bus / 无消费者孤岛 | code/data 4条WARN(08-04), 丰碑/data 0B, iso-sand 2条(07-22) |
| 胶水层架构干净但未运行 | glue_server.py(未启动); 仅 glue_server+tests 引用 interfaces |
| 胶水层硬编码向量内网 IP | glue_server.py:34 `192.168.0.103:11435` |
| 沙漏纯内部自愈 | sandglass_source/nightwatch.py (阴影副本/末行修复) |
| 沙漏零依赖跨平台 | sandglass_source/heartbeat.py:3-5 |
| LMS 内部做梦调度 | living-memory-system-cloud/runtime/dream_scheduler.py |
| verify_daemon 独立 seek 消费 | AgentOS-IsoSand/同构沙盘/src/verify_daemon.py:42-44 |
| verify_daemon cwd 依赖 + 硬编码内核路径 | verify_daemon.py:44,48 |

---

## 四、系统论结论（dandan 核心关切）

### A. 事件总线 / 调度器 / 胶水层的真实关系

**真相：不是"三重复"，是"一个骨架 + 一个断头生产者 + 一个待机收口层"。**

- **iso-sand 事件总线 = 唯一活着的骨架**（调度+消费者在跑）。它是"总线 = 骨架"的正确形态。
- **丰碑/code/event_bus = 骨架的失控双胞胎**（真重复，头号问题）——同一总线逻辑被复制并演进到 v0.6.0，但没接上线，还把 `data` symlink 到 iso-sand。**必须治理，否则双维护 + 双写风险。**
- **xuanjian_pipe = 最重要的生产者写进了死胡同**：玄鉴知识本应是总线最核心的事件，却写进 `丰碑/code/data/event_bus.jsonl` 无人消费。这是"生产者认错总线"的断头。
- **胶水层（interfaces + glue_server）= 正确的"端口+适配器"层，但断电待机**。它不是重复，而是**未缝合的收口层**。它既是记忆编排的出口，也天然是 `producer→event→consumer` 的 **handler 接口宿主**（待 M3 接入）。
- **结论**：`调度器=时钟`、`总线=骨架`、`胶水层=记忆编排(收口)` 三者**互补未缝合**，而非重复。缺的一块是「统一 producer/handler 接入协议」（M2 借鉴①②的落点）。

### B. 玄鉴 / LMS / 沙漏 / iso-sand 的真实关系

**结论：合理分层，无真重复，但存在被"调度/心跳/消费者"同名表象掩盖的异构实体。**

- 合理分层（各司其职，不重复）：
  - **沙漏** = 显式叙事记忆 + 自愈（heartbeat/nightwatch 是它内部命脉）。
  - **LMS** = 隐式塑形记忆 + 做梦（dream_engine/dream_scheduler 是它内部运算）。
  - **玄鉴/verify_daemon** = 内核级"是否忠实执行"校验（消费文件变更日志）。
  - **iso-sand 总线** = 跨系统信号骨架（调度/通知）。
- **假重复（该护，禁止统合）**：沙漏心跳 / LMS 做梦 / verify_daemon 校验——全是**子系统内部自维护闭环**。统合 = 把各系统命根子外包，破坏内聚（对应全局设计初步判断"假重复不该动"✅ 已证实）。
- **同名异构需要区分**：'task_scheduler'(iso-sand执行shell) vs 'dream_scheduler'(LMS 空闲记忆运算)、'event_consumer'(事件) vs 'verify_daemon'(文件变更) vs 沙漏'heartbeat'(健康)。它们只是**共享"消费者+offset/定时"这个通用模式**，语义域完全不同——这是"表面相似、实为异构"的假重复，不该揉成一个。

### C. 哪些「重复」不该统合（保护它们）

1. **沙漏 heartbeat / nightwatch** —— 自愈命脉，保护。
2. **LMS dream_engine / dream_scheduler** —— 记忆运算内核，保护。
3. **verify_daemon 的文件变更校验** —— 玄鉴忠实性校验，保护。
4. **各系统内部 `payload` schema 自由度**（`payload: object`）—— 保护，勿锁死。

### D. 哪些「缺口」该统合（真缺口清单）

| # | 缺口 | 该处置 |
|---|------|--------|
| D1 | **总线物理文件碎片化**（4 个 event_bus.jsonl） | 归并为统一总线文件/统一可配置地址；生产者统一认一个总线 |
| D2 | **xuanjian_pipe 写进死胡同** | 把玄鉴事件发布到被消费的主总线（最高价值生产者） |
| D3 | **丰碑/code/event_bus fork 双维护** | 冻结/砍掉 fork；把它安全加固（exec+script）移植回主消费者 |
| D4 | **胶水层通电接入总线** | 启动 glue_server；以 hexagon handler/接口取代 shell 命令 |
| D5 | **monument_bridge Windows 路径** | 改为相对/可配置（消除跨机碎片化） |
| D6 | **消费者 shell 动作 → handler 接口** | 按 M2 借鉴②升级；shell 降为一种 handler |
| D7 | **事件契约版本化 + event_type 注册表 + 幂等去重** | 补 M2 借鉴③三件套 |

---

## 五、对「上一位审计员线索」的验证与修正

| 线索 | 原判断 | 我的验证 | 结论 |
|------|--------|----------|------|
| 线索① 多个 event_bus.jsonl 碎片化 | ✅ | 坐实，且更严重：**4 个物理文件** + 2 套 fork 代码 | ✅ 采纳（详见二.5） |
| 线索② consumer 不在 ps | iso-sand consumer 没跑 | **PID 1641746 在跑**（Jul22 起，3:28 CPU） | ❌ **修正**：scheduler(1641741)+consumer(1641746) 都在跑；但**任务列表为空、消费的是 iso-sand 自己的死总线**（无外部生产者） |
| 线索③ 胶水层只被 score_examples 引用 | 只辖记忆域待验证 | **实际被 glue_server.py + tests 引用**，`glue_server.py` 未启动 | ⚠️ **部分修正**：胶水层确实未接入 OpenClaw 运行时（待机），但引用面不止 score_examples |
| 线索④ monument_bridge Windows 路径 | Z:\QH | **坐实**：monument_bridge.py:40 `r"Z:\QH\AI专用\Agent OS\iso-sand"` | ✅ 采纳 |

> 关键的新认知：**总线不是"没在跑"，而是在跑一个没接入生产者的空壳**。真正的问题不是"总线没起"，而是"最重要的生产者（xuanjian）把事件写到了没人的地方，最重要的收口层（胶水层）没通电"。这比"消费者没跑"更隐蔽、也更该修。

---

## 六、给 M3 设计的直接落点（一句话版）

1. **保留并巩固** iso-sand 的 `jsonl+seek+死信+重试+限流` 轻量总线骨架（它方向正确，等价轻量 Kafka）。
2. **统一总线归属**：消除 4 个 event_bus 文件 + 2 套 fork，只留**一个权威总线 + 一套消费者代码**（把 v0.6.0 安全加固迁回主消费者）。
3. **让 xuanjian_pipe 回归主总线**：玄鉴事件发布到统一总线，作为最高价值 producer。
4. **给胶水层通电**：把 `Interfaces/glue_server` 作为 Hexagonal handler 宿主接入总线（shell 降级为一种 handler）。
5. **护住**单沙漏心跳 / LMS 做梦 / verify_daemon 校验——绝不动，只做「事件通知」观测。
6. **补契约三件套**：schema_version / event_type 注册表 / 幂等去重（按 M2 借鉴③）。

---

## 附：审计方法说明
- 全部为**只读**探查（read/cat/grep/ps/diff），未修改任何文件、未启动/停止/变更任何服务。
- 唯一的新落盘文件 = 本报告 `audit-M1-模块功能审计.md`。
- 供 M3 设计整合；源码证据均可复现（文件+行号见第三节汇总表）。
