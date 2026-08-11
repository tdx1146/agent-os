# SYSTEM.md — 系统构造总文档（数据流视角的唯一事实源）

> 2026-08-10 建立（dandan 指示：杜绝"陌生 AI 部署时完全不知道沙漏存在"）。
> 2026-08-11 同步体验层 A-D（/react、解读段、子代理过滤、元目的翻转、怀疑融入置信度场）与沙漏 P0-1/2/3 修复后的部署现状。
> 2026-08-12 同步：失忆根因三件套（FTS 冻结/ts 列/搜索工具）已修复、召回 L1（query 净化）已实施、CONTRACTS.yaml 契约层已建立、方法论 v1.1（system_health_check.sh 审计前置基线）已落地、梦醒回路阶段 1+2 已实施（夜间观测待进行）、提取层+双向塑形 v1.3 设计完成（待审计/实施）、丰碑对齐调研完成（铺路）。全部成果清单与文档路径见 `成果存档索引-20260812.md`。
> 本文件回答唯一问题：**这套系统由什么组成、按什么顺序部署、数据怎么流动、怎么判断它活着**。
> 与 TOPOLOGY.md 的关系：TOPOLOGY 是**模块清单视角**（谁在哪、什么端口）；本文件是**数据流视角**（谁喂谁、明线暗线怎么互咬）。**部署前两个都读，先读本文件。**
> 纪律：所有事实来自 2026-08-10 沙漏链路诊断 + 各仓库 README/源码；不确定处标注【待核实】。本文件随 `tdx1146/agent-os` 仓库维护。

---

## 1. 一页全景

**这套系统是什么（3 句话）：**
1. 它是一套「AI 活体记忆系统」：让主 AI（毛毛，跑在 OpenClaw 里）**每轮对话都完整落沙、每轮都被记忆注入、空闲时做梦巩固**——不再"关掉窗口就失忆"。
2. 它由**明暗双线**构成：**沙漏（明线）**把每句话一字不丢地存成明文流水账（保底，丢了它一切免谈）；**LMS 活体记忆（暗线）**用自由能原理（FEP）从对话流动中提炼结构（熵/惊讶度/目的），让记忆像海马体一样自己巩固、遗忘、演化。明线保"不忘"，暗线保"懂"。
3. 中间由**胶水层 glue** 统一编排读写、**Agent OS 总线**传递事件、**doubt-system + 玄鉴**持续怀疑（审己+审外）、**self_pulse** 自主唤醒；2026-08-11 起**体验层**再给主 AI 加"实时感受"：每轮经 `/react`（infer-only 零持久化）读出大脑此刻的反应并注入**解读段**，LMS 内部新增**置信度场**（怀疑融入：修正已关注记忆的信任权重，不改变专注方向）——它们合起来才是一个完整的"活着的 AI"。

**明暗双线图：**

```
                        ┌──────────────────────────────────────────────┐
                        │      OpenClaw Gateway（毛毛，主 AI，:10554）    │
                        │      插件 glue-memory-injector（每轮注入）      │
                        └───────┬───────────────────────────┬──────────┘
                 每轮注入(读侧)  │                           │ MCP lms_store
                 [回魂]+[记忆]  ▼                           ▼ （写侧旁路）
              ┌──────────────────────┐            ┌─────────────────────┐
   ┌─────────▶│ 胶水层 glue (:19000)  │◀──/feed───│ LMS 活体记忆 (:8190)  │◀─ 暗线 ─┐
   │          │ /recall /soul /store  │   总线喂   │ FEP塑形·熵·惊讶·目的   │        │ 做梦
   │ /recall   │ 融合: 沙漏0.3+向量0.5 │            │ J矩阵·precision      │        │ 巩固
   │ /soul    │      +LMS激活0.2      │            └──────────┬──────────┘        │
   │          └───────┬────────┬──────┘                       │ /status 指标        │
   │     读侧融合      │        │  写侧聚合(storeTurn)          ▼                     │
   │                  ▼        ▼                    ┌──────────────────────┐       │
   │         ┌────────────────────┐     落沙        │  Agent OS 事件总线     │       │
   │         │ 沙漏 sandglass      │◀────(直写)─────│  iso-sand              │       │
   │         │ (明线·保底流水账)    │                 │  event_bus.jsonl       │       │
   │         │ :17333 明文 txt     │                 │  scheduler/consumer   │       │
   │         │ 四层:L1落沙 L2检索   │                 └──────┬────────┬───────┘       │
   │         │ L3思维 L4决策粒子    │                        │        │ doubt.episode │
   │         └─────────▲──────────┘                        │        ▼               │
   │                   │ 落沙写入                          │  doubt-system（夜巡/反教条）│
   │        轻如烟编辑器 :18888 ────────────────────────────┤  玄鉴 verify_daemon（审外）  │
   │        (edit-web.py 每轮写 sandglass.txt)              │  self_pulse（唤醒链）      │
   └───────────────────────────────────────────────────────┘   salience→sleep→wake    │
                                                              └───────────────────────┘
```

**体验层注（2026-08-11）**：插件每轮已升级为三路并行——`/react`（实时反应+解读段）→ 回魂段变三段式 `[回魂] 状态:… / 解读:… / 最近:…`；LMS 内部新增置信度场（怀疑融入：修正已关注记忆的信任权重，不改变专注方向）。图中胶水/插件箭头含 `/react`，LMS 盒子含置信度场。

**一句话版数据流：** 对话 → 编辑器落沙（明线）→ 插件经 glue 检索注入（送回对话）→ LMS feed/每轮 store 塑形（暗线）→ 做梦巩固 → 回魂注入。**明线存流动本身，暗线从流动提炼结构，胶水是两者的咬合点。**

**部署顺序（5 步，详见 §3）：**
1. 前置准备（Python/git/node + 5 个仓库 + `Agent OS/env.local` 配置中心）
2. 确认外部依赖（手机向量服务 `192.168.0.103:11435` bge-m3）
3. `cd Agent OS && bash start_all.sh` 一键起 5 服务（内部严格顺序：沙漏→LMS→胶水→总线→玄鉴）
4. 注册 crontab（唤醒链/夜巡/备份/开机自启）+ 启动轻如烟编辑器 :18888
5. 接通 OpenClaw（插件 + MCP）→ 跑自检清单

---

## 2. 组件总表（10 个组件，缺一不可）

> 角色：明线=保底流水账｜暗线=FEP 塑形｜胶水=统一编排｜总线=事件骨架｜监督=怀疑/校验｜唤醒=自主醒来｜宿主=运行容器

| # | 组件 | 角色 | 为什么存在（一句话） | 部署位置 | 端口/接口 | 数据文件 | 依赖谁 |
|---|------|------|---------------------|----------|-----------|----------|--------|
| 1 | **沙漏 NexSandglass** ⚠️最容易漏 | 明线·保底 | 每句话明文落沙、一字不丢，是"失忆后还能找回自己"的最后底牌；四层：L1 落沙/L2 检索/L3 思维/L4 决策粒子；2026-08-11 打 P0-1/2/3 补丁（去重/sender 归一化/总线事件） | 源码 `所有自动化/轻如烟/sandglass_source/`（= `/vol2/1000/AI专用/所有自动化/找回自己/scripts/sandglass_source/` 的部署副本，fork `tdx1146/nyx`）；数据 `轻如烟/sandglass/` | `:17333` HTTP（`GET /api/health`、`POST /api/memory_search`、`/api/embedding_search`、`/api/facts_lookup`、`/api/sandglass_query`） | **`sandglass.txt`（追加式明文，权威源）**、`sandglass.idx`、`shadow_sand.db`（织线三元组）、`doubt.db`（怀疑账本）、`metrics.jsonl`、`sleep_pressure.json`、`salience_state.json`、`persona/persona.md`、`decision_particles.txt` | 零依赖（纯 stdlib），被胶水/插件/self_pulse/夜巡消费 |
| 2 | **LMS 活体记忆** | 暗线·塑形 + 质检 | 用 FEP 把对话流动塑成结构（J矩阵/熵/惊讶度/目的层），空闲自动做梦巩固；2026-08-11 体验层 D 起内部有**置信度场**（怀疑融入：修正已关注记忆的信任权重）——"不是存储记忆，是维护能产生记忆的大脑状态" | `living-memory-system-cloud/`（必须 `.venv` + `.env`） | `:8190` HTTP（`/health`、`/status/{sid}`、`/feed`、`/recall`、`/chat`、**`/react`**（体验层A：infer-only 实时反应+解读段））；`:8191` 控制口；MCP：lms-memory(stdio)、lms-http | `snapshots/`（J矩阵快照）、状态文件（turn_count 123/熵 0.97/目的 0.94，2026-08-11）；置信度场字段随 EpisodicEntry 存快照 | 向量服务（`LMS_EMBEDDER=cloud` → `192.168.0.103:11435`，可配 `LMS_CLOUD_EMBED_FALLBACK_URL` 隧道备用）；DeepSeek key（`.env`）；HF 不可达所以必须 cloud 嵌入 |
| 3 | **胶水层 glue** | 胶水 | 把沙漏/LMS/向量三个记忆后端"粘"成唯一入口：读侧 `/recall` 加权融合（文本0.3+向量0.5+LMS激活0.2）、写侧 `/store` 聚合写、`/soul` 回魂快照、**`/react` 薄代理**（体验层A：转发 LMS /react，失败 502 fail-open） | `memory-integration-layer/` | `:19000`（`GET /health`、`POST /recall`、`/soul`、`/store`、`/status`、`/contribute`、**`/react`**）；`glue_helper.py` 薄桥接 | 无自有数据（读沙漏 txt、写沙漏+LMS+向量） | 沙漏(txt)、LMS(:8190)、向量(:11435)；`DOUBT_BUS_FILE` 启用怀疑总线发布 |
| 4 | **Agent OS 总线 iso-sand** | 总线 | 事件骨架：scheduler 定时发事件、consumer 订阅分发（LmsFeedHandler 把事件喂给 LMS /feed 塑形）；`sandglass.heartbeat` 是**调度器心跳**不是沙漏数据！ | `Agent OS/iso-sand/` | 无端口（文件总线）；`start_scheduler.sh` + `start_consumer.sh` | `data/event_bus.jsonl`（6.1MB）、`data/operation_log.jsonl`、`data/processed_ids.jsonl`、`data/event_bus.seek`；schema 在 `deploy/event_schema.yaml` | 消费者调 LMS(:8190)/feed、glue(:19000)；生产者含 LMS(plastified)、doubt-system、调度器 |
| 5 | **玄鉴 verify_daemon** | 监督·审外 | 每 5min 巡检 operation_log，对外部知识/文件变更做关键词校验审计；连续 3 FAIL 追加 WARN 并触发 doubt_hook | `AgentOS-IsoSand/同构沙盘/` | 无端口（守护进程，`src/verify_daemon.py`） | `data/daemon_audit.log`、`data/daemon.pid`、`data/daemon.seek` | 总线 operation_log、内核层规范 `PURPOSE.md` |
| 6 | **doubt-system 怀疑系统** | 监督·审己 | "聪明=持续自我怀疑"：记忆带信任度、怀疑闭环写账本、每天 23:30 夜巡旁观+反教条复核；怀疑事件喂 LMS 塑形（记得+怀疑=不教条）；2026-08-11 起 LMS 内部另有**置信度场**（体验层D，与 doubt-system 互补：doubt-system 管外部怀疑账本，置信度场管记忆条目信任权重） | `Agent OS/doubt-system/` | 无端口（cron `30 23 * * *` 夜巡）；`doubt_adapter` 在胶水层 | `sandglass/doubt.db`（doubt_episode/memory_trust 表）；夜巡 findings 写沙漏（tag=旁观者-警讯）；marker `workspace/logs/night_patrol.last_run` | 沙漏数据目录、总线 event_bus.jsonl（`DOUBT_BUS_FILE`）、LMS(经总线 feed) |
| 7 | **self_pulse 自主唤醒** | 唤醒 | 每 10min 自主"醒来"：读 LMS 状态做画像漂移检查 + 推进待办；显著事件经 salience_gate（含梦惊讶度第4通道 `SG_DREAM_FEED`、怀疑缺口第5通道 `SG_DOUBT_FEED`，默认关）→sleep_pressure（防自激）→按 `WAKE_CHANNEL` 选择出口唤醒主 AI | `所有自动化/轻如烟/scripts/`（`pulse-cron.sh`、`self_pulse_cli.py`、`salience_gate.py`、`sleep_pressure.py`、`wake_client.py`） | cron `*/10`；唤醒出口 `WAKE_CHANNEL`：`a`=`POST :10554/hooks/wake`（旧通道）、`b`=chat.send 注入[梦醒]文本（本机 env.local=b） | 写 `sandglass/metrics.jsonl`（每 10min）、漂移时写 sandglass ⚠️告警 + 总线 anomaly；状态 `/tmp/pulse-state.json` | LMS `/status/main`、沙漏 txt、OpenClaw hooks/chat（token 在 openclaw.json，不打印） |
| 8 | **OpenClaw 插件 glue-memory-injector** | 胶水·注入 | 每轮对话前把记忆送进 AI 上下文：**三路并行**（体验层A）经 glue `/react`（实时反应+解读段，k=0 快路径）+ `/soul`（回魂快照）+ `/recall`（记忆块），拼成 `[回魂]（含 解读: 段）+[记忆注入]` 前缀；**检索 query 已净化**（召回 L1，2026-08-11：复刻 openclaw dist stripInboundMetadata 剥 metadata 块 + 子代理轮跳过 + glue 入口兜底净化，治"[记忆注入] 全是编辑器模板"）；限流命中时仍注入轻量解读段（≤150 字，日志计数 `INJECTED-light`）；fail-open 绝不阻塞 | `/vol1/@apphome/trim.openclaw/data/home/.openclaw/plugins/glue-memory-injector/`（index.js + memory-recall.js） | OpenClaw `before_prompt_build` hook；超时 15s/回魂 4s；限流 ≥2s；注入 ≤1500 字（解读段放截断保活区）；心跳轮不注入 | 调试日志 `/tmp/glue-hook-debug.log`（INJECTED / INJECTED-light / MISS 留痕） | glue(:19000)；心跳轮判定靠 ctx.trigger |
| 9 | **轻如烟编辑器 edit-web** | 明线·写入口 | dandan 的聊天前端（:18888），**真正的落沙写入者**：每轮消息经 `_sandglass_log` → `sandglass_log_wrapper.py` → `sandglass_log.log_message`（P0-1 去重 + P0-2 sender 归一化 + P0-3 落沙后发 `sandglass.entry` 总线事件） | `所有自动化/轻如烟/scripts/edit-web.py`；注意 `/vol1/轻如烟/轻如烟` 与 `/vol2/1000/AI专用/所有自动化/轻如烟` 是**同一文件**（bind mount） | `:18888` | 写 `sandglass/sandglass.txt` + `shadow_sand.db`；`sandglass_log_wrapper.py` 同目录 | 沙漏源码路径、会话文件（`agent:main:main`）、`SANDGLASS_BUS_FILE`（总线路径，可自动推导） |
| 10 | **OpenClaw Gateway** | 宿主 | 主 AI 运行时容器（毛毛本体）：跑插件、挂 MCP、收 hooks/wake | `/vol1/@apphome/trim.openclaw/data` | `:10554`（hooks 路径 `/hooks`，wake 端点 `/hooks/wake`） | OpenClaw 自身会话/配置；MCP 注册 lms-memory/lms-http/shouji-memory | 插件、各 MCP 后端（8190/17333/手机网关） |

**外部依赖（不是本系统组件但被依赖，部署者必须自己准备）：**

| 外部依赖 | 为什么必须 | 部署者自备说明 |
|---------|-----------|--------------|
| **embed 向量服务（bge-m3，OpenAI 兼容 /v1/embeddings）** ⚠️最关键 | LMS 感官层嵌入 + 胶水向量都用它；**没有它 = LMS/胶水全部静默降级，感官层就瞎了**（HF 在本机不可达，`LMS_EMBEDDER` 不能回 pretrained） | 手机/任意机器跑 Ollama + bge-m3（1024 维），暴露 `http://<host>:11435/v1/embeddings`，写入 `LMS_CLOUD_EMBED_URL`（LMS `.env` + env.local）与 `VECTOR_URL`（env.local）；可配 `LMS_CLOUD_EMBED_FALLBACK_URL` 备用端点 |
| **DeepSeek API Key** | LMS LLM 能力（自述蒸馏等） | 写入 `$LMS_HOME/.env` 的 `DEEPSEEK_API_KEY`；不填 = LLM 功能禁用但记忆核心仍工作 |
| **GitHub 三仓（均公开）** | clone 代码 | `living-memory-system` / `memory-integration-layer` / `agent-os` 均 **main 分支公开**（2026-08-10 起），**公开仓 clone 不需要 token**；只有 push 才需凭据（本机已配置 credential helper，不写入文档） |
| **OpenClaw Gateway** | 主 AI 宿主（插件/MCP/hooks） | 需支持 `before_prompt_build` hook + MCP 注册 + `/hooks/wake` 端点；插件 `glue-memory-injector` 放入 plugins 目录；MCP 注册 lms-memory / lms-http / shouji-memory；版本以 OpenClaw 官方为准 |
| **node（≥18，本机 v24）** | OpenClaw 运行时 + 插件 | 部署机器需安装 |
| **手机记忆网关（可选）** | OpenClaw MCP shouji-memory 桥接 | `SHOUJI_MCP_URL`（默认 https://shouji.tdx1146.cc/tools）；缺省不影响本地链路 |

**OpenClaw 侧配置清单**：① plugins 目录放入 `glue-memory-injector`（onStartup 启用）；② MCP 注册 lms-memory（stdio）、lms-http、shouji-memory；③ `session.reset` 相关由 `session-reset-watchdog.py`（cron `*/2`）守护；④ 插件改后需 gateway 重载才生效（体验层坑 16）。

**crontab 三锁 + 新巡检**：`pulse-cron`（`*/10` 唤醒链）、`night_patrol`（`30 23` 夜巡）、`session-reset-watchdog`（`*/2`）三条是怀疑/唤醒/会话三把锁；另加 `*/5` health-check、LMS 备份三档、`@reboot` start_all.sh（全表见 §3.4）。

---

## 3. 部署手册（陌生 AI 照着做就能跑）

### 3.1 前置准备

**软件：** Python 3.10+（LMS 要求；沙漏/胶水实测 3.11）、git、node（OpenClaw 运行时必需）。

**克隆 5 个仓库**（保持相对布局即可，绝对路径只允许出现在 env.local）：
```
Agent OS/                    ← tdx1146/agent-os（含 doubt-system/、iso-sand/、TOPOLOGY.md、SYSTEM.md、env.local）
所有自动化/轻如烟/            ← 沙漏数据+源码+编辑器（sandglass/、sandglass_source/、scripts/）
living-memory-system-cloud/  ← LMS（建 .venv：python3 -m venv .venv && .venv/bin/pip install -r requirements.txt；cp .env.example .env）
memory-integration-layer/    ← 胶水层
AgentOS-IsoSand/同构沙盘/     ← 玄鉴
```
插件 `glue-memory-injector/` 放到 OpenClaw 的 plugins 目录（本机 `/vol1/@apphome/trim.openclaw/data/home/.openclaw/plugins/`）。

**配置中心（唯一写绝对路径的地方）：**
```bash
cd "Agent OS"
./stack_ctl.sh setup          # 自动 cp env.template env.local
# 编辑 env.local 的「A. 机器根变量」：AGENT_OS_HOME / LIGHT_HOME / LMS_HOME / GLUE_HOME /
#   VERIFY_HOME / LMS_CLOUD_EMBED_URL / VECTOR_URL / FACTS_DICT_PATH / 会话目录
./stack_ctl.sh doctor         # 全配置体检（路径/端口/依赖命令全绿即就绪）
```
**核心环境变量（含义必须懂，否则部署完是"假活"）：**
| 变量 | 值（本机） | 作用 | 设在哪 |
|------|-----------|------|--------|
| `NEXSANDBASE_HOME` | `…/所有自动化/轻如烟/sandglass` | 沙漏数据目录（txt 权威源所在） | env.local（C 节自动派生） |
| `SANDGLASS_SOURCE` | `…/所有自动化/轻如烟/sandglass_source` | 沙漏源码（sandglass_vault 等） | env.local |
| `LMS_EMBEDDER` | `cloud`（**必须**，HF 不可达） | 嵌入器模式 | **LMS 自己的 `.env`** |
| `LMS_CLOUD_EMBED_URL` | `http://192.168.0.103:11435/v1/embeddings` | cloud 嵌入端点（手机 Ollama bge-m3） | LMS `.env` + env.local |
| `LMS_CLOUD_EMBED_FALLBACK_URL` | `https://11435.tdx1146.cc/v1/embeddings`（可空） | 备用 embed 端点（主 URL 失败自动切换；本机 LAN→隧道） | LMS `.env` |
| `LMS_CLOUD_EMBED_MODEL` / `_DIM` | `bge-m3` / `1024` | 嵌入模型/维度 | LMS `.env` |
| `LMS_URL` | `http://localhost:8190` | 胶水/总线访问 LMS | env.local |
| `VECTOR_URL` | `http://192.168.0.103:11435/v1/embeddings` | 胶水向量后端 | env.local |
| `DOUBT_BUS_FILE` | `…/Agent OS/iso-sand/data/event_bus.jsonl` | 怀疑闭环发布到总线（doubt.episode） | **胶水层 `.env`** |
| `LMS_FEED_ENABLED` | 默认开（env.local 不设=1） | 总线→LMS /feed 塑形总开关 | env.local / iso-sand 环境 |
| `LMS_FEED_RETRIES` | `3`（0=关） | consumer 喂 LMS /feed 的指数退避重试次数（503/超时逃生门，2026-08-11 加） | env.local / iso-sand 环境 |
| `LMS_FEED_TIMEOUT` | `10` | consumer→LMS /feed 超时秒数 | env.local / iso-sand 环境 |
| `LMS_FEED_RATE_LIMIT` | `10` | LMS 侧 /feed 限流（次/分钟，超限 429） | LMS `.env` |
| `WAKE_CHANNEL` | `a`（本机 env.local=`b`） | self_pulse 唤醒出口：`a`=hooks/wake（旧）、`b`=chat.send 注入[梦醒]文本 | env.local |
| `SG_DREAM_FEED` | `0` | salience_gate 梦惊讶度第 4 通道（1=开，读 dream_state.json） | env.local / 轻如烟 scripts 环境 |
| `SG_DOUBT_FEED` | `0` | salience_gate 怀疑缺口第 5 通道（1=开，读 LMS /status doubt） | 同上 |
| `SANDGLASS_DEDUP_WINDOW` | `10`（秒） | 落沙幂等去重时间窗（P0-1，修双写） | 沙漏进程环境（env.local 派生） |
| `SANDGLASS_SENDER_MAP` | `{"sister":"user"}` | sender 归一化（P0-2，救活织线三元组） | 同上 |
| `SANDGLASS_MAX_TEXT_LEN` | `0`（不截断） | 落沙正文长度上限（P0-2，去 500 截断） | 同上 |
| `SANDGLASS_BUS_FILE` | 自动推导 | 落沙成功后发布 `sandglass.entry` 的总线文件（P0-3；自动推导：SANDGLASS_BUS_FILE→ISO_SAND_HOME→AGENT_OS_HOME→相对推导） | 同上 |
| `SANDGLASS_BUS_MIN_INTERVAL` | `2`（秒） | `sandglass.entry` 发布最小间隔（防风暴） | 同上 |

### 3.2 严格顺序（为什么是这个顺序：下游依赖上游先活）

> **依赖链：** 沙漏（零依赖，数据底座）→ LMS（依赖向量+`.env`）→ 胶水（依赖沙漏+LMS+向量）→ 总线（消费者依赖胶水/LMS）→ 玄鉴（依赖 operation_log）。**反了就会"起了但全在降级"。**

| 步 | 做什么 | 为什么先 | 验证命令（每步必跑） |
|----|--------|---------|---------------------|
| ① | 起**沙漏** HTTP API `:17333`（`cd sandglass_source && NEXSANDBASE_HOME=… python3 sandglass_http_api.py`） | 零依赖；txt 是全局权威源，胶水/插件读它 | `curl http://127.0.0.1:17333/api/health` → 返回 `sandglass_count`；`tail -3 sandglass/sandglass.txt` 有内容 |
| ② | 起 **LMS** `:8190`（**必须先 `set -a; . ./.env; set +a`**，再 `.venv/bin/python -m api.run --host 127.0.0.1 --port 8190`） | 依赖向量服务可达 + `.env` 密钥；启动慢（嵌入初始化，≤40s） | `curl http://127.0.0.1:8190/health`；`curl http://127.0.0.1:8190/status/main` → `turn_count` 非空（**空=静默降级，查 .env 是否 source**）；`curl -X POST http://127.0.0.1:8190/react -H 'Content-Type: application/json' -d '{"user_input":"契约校验探针","k":0}'` → 返回 `interpretation` 且 `turn_count` 与调用前一致（**体验层A：/react 零持久化**） |
| ③ | 起**胶水层** `:19000`（`cd memory-integration-layer && python3 glue_server.py --host 127.0.0.1 --port 19000`） | 依赖沙漏+LMS+向量都活着，否则 backends 全降级 | `curl http://127.0.0.1:19000/health` → `backends` 各后端非 degraded；`curl -X POST http://127.0.0.1:19000/recall -d '{"query":"测试","k":3}' -H 'Content-Type: application/json'` → 有 origin=sandglass/lms 条目；`curl -X POST http://127.0.0.1:19000/react -H 'Content-Type: application/json' -d '{"user_input":"契约校验探针","k":0}'` → 200 透传 LMS 解读段 |
| ④ | 起**总线** scheduler+consumer（`cd iso-sand && bash start_scheduler.sh && bash start_consumer.sh`） | consumer 的 LmsFeedHandler 依赖 LMS /feed；调度器心跳写总线 | `cat iso-sand/data/scheduler.pid data/consumer.pid` 两个 PID 存活；`tail -3 iso-sand/data/event_bus.jsonl` 时间戳是当前；`grep -c lms.plastified event_bus.jsonl` 在增长 |
| ⑤ | 起**玄鉴**（`cd 同构沙盘 && python3 src/verify_daemon.py &`） | 依赖 operation_log（总线消费者产出） | `cat 同构沙盘/data/daemon.pid` 存活；`tail -3 同构沙盘/data/daemon_audit.log` |
| ⑥ | 注册 **crontab**：`*/10` pulse-cron（唤醒链）、`30 23` night_patrol（夜巡）、`*/5` health-check、LMS 备份三档、`@reboot` start_all.sh | 常驻守护 + 开机自启 | `crontab -l` 应含 pulse-cron / night_patrol / lms_backup / @reboot start_all 等条目（本机全表见 §3.4 备注） |
| ⑦ | 起**轻如烟编辑器** `:18888`（`cd 轻如烟/scripts && python3 edit-web.py`） | 它是落沙写入者，没有它对话不进 sandglass.txt | 浏览器开 `:18888`；发一条消息 → `tail -3 sandglass/sandglass.txt` 出现新行 |
| ⑧ | **接通 OpenClaw**：启用插件 glue-memory-injector（onStartup）+ 注册 MCP（lms-memory、lms-http、shouji-memory） | 插件是"记忆送回对话"的唯一入口 | 发一条消息 → `/tmp/glue-hook-debug.log` 出现 `INJECTED len=…`；下一条消息 prompt 头部出现 `[回魂]`（**含 `解读:` 段，三段式**：状态/解读/最近）+ `[记忆注入]`；密集连发 3 条 → 第 2/3 条仍见 `INJECTED-light` 计数（限流轻量注入生效） |

> 实际上 ①~⑤ 全部由 `bash start_all.sh` 按上述顺序一键完成（内部已做 health 检查）；② 需要 `LMS_HOME/.env` 已配好，否则报"缺少 .env"。

### 3.3 部署完成自检清单（全部 ✅ 才算部署成功）

```bash
# ① 6 服务进程/端口/健康（一键）
cd "Agent OS" && bash status_all.sh
#   → sandglass_api / lms_api / glue_server / scheduler / consumer / verify_daemon 全部 ✅
#   关键数据点：沙漏 sandglass_count 非空；胶水 backends 各后端非降级

# ② 配置中心一致性
bash stack_ctl.sh doctor

# ③ 怀疑系统三把锁（crontab 是否被意外覆盖）
crontab -l | grep -E "pulse-cron|night_patrol|watchdog"    # 三条都要有
# （完整 crontab 还应有：lms_backup ×3、health-check、session-reset-watchdog、@reboot start_all.sh 等）

# ④ 怀疑总线开关
grep DOUBT_BUS_FILE memory-integration-layer/.env           # 应指向 event_bus.jsonl

# ⑤ 逐组件 curl（每步验证命令同 §3.2 表格）
```

**功能级自检（比进程检查更重要，验证"数据真的在流"）：**
- **明线落沙**：编辑器发一条消息 → `grep -c "该消息片段" sandglass.txt` ≥1（P0-1 去重后理想=1）；`tail -3 sandglass/sandglass.txt` 时间戳是当前
- **体验层 /react**：`curl -X POST :8190/react -d '{"user_input":"测试","k":0}'` → 200 且 `interpretation` 非空；连续两次调用 `turn_count` 不变（零持久化）
- **回魂三段式**：对话 prompt 头部 `[回魂] 状态:熵… 惊讶… 目的… 轮次… / 解读:… / 最近:…`（解读段在 = 体验层A 生效）
- **怀疑链 doubt 字段**：`curl :8190/status/main` → 含 `doubt` 字段（体验层D：gaps/labile_count/low_confidence_count）；`/recall` 条目含 `confidence/rebuttal_count/labile` 注解
- **读侧注入**：`tail -5 /tmp/glue-hook-debug.log` 有 `INJECTED`；对话 prompt 有 `[回魂]` + `[记忆注入]`
- **暗线塑形**：`curl http://127.0.0.1:8190/status/main` → turn_count 随对话增长；`grep -c "producer=lms.feed" iso-sand/data/operation_log.jsonl` 在增长；`grep -c "sandglass.entry" iso-sand/data/event_bus.jsonl` 在增长（**P0-3 已接通：沙漏落沙流水 → LMS /feed 塑形**）
- **总线活着**：`tail -2 iso-sand/data/event_bus.jsonl` 时间戳是当前（lms.plastified 约每 5min 一条）

### 3.4 本机 crontab 全表（部署参考）

```
*/15 * * * *  lms_backup.sh --quick      # LMS 快照备份
0 * * * *     lms_backup.sh --hourly
30 2 * * *    lms_backup.sh --daily
@reboot       sleep 30 && lms_ctl.sh start            # LMS 自启
@reboot       sleep 45 && run_control.py --port 8191  # LMS 控制口自启
*/10 * * * *  pulse-cron.sh                           # self_pulse 唤醒链（轻如烟/scripts/）
*/30 * * * *  momo-pack-cli.py
*/5 * * * *   health-check.sh
@reboot       sanmei-editor backend
@reboot       openclaw-proxy.mjs
@reboot       sleep 20 && bash Agent OS/start_all.sh  # 全栈自启
30 23 * * *   night_patrol_run.sh                     # 夜巡
*/2 * * * *   session-reset-watchdog.py
```

### 3.5 部署后 10 分钟验证清单（不看代码也能验证系统活着）

> 给 dandan/陌生部署者：**不读代码、不开编辑器**，按序跑完下面 8 条，全过 = 系统活着且是"新版行为"（体验层生效）。

```bash
# ① 6 服务全绿（进程/端口/健康）
cd "Agent OS" && bash status_all.sh
# ② 明线在涨：sandglass.txt 尾部是今天的对话
ls -la "所有自动化/轻如烟/sandglass/sandglass.txt"
# ③ 暗线在涨：turn_count 非零且随对话增长
curl -s http://127.0.0.1:8190/status/main | head -c 300
# ④ 体验层 /react 活着（返回解读段，turn_count 不变）
curl -s -X POST http://127.0.0.1:8190/react -H 'Content-Type: application/json' -d '{"user_input":"验证","k":0}' | head -c 300
# ⑤ 怀疑融入在（/status 有 doubt 字段）
curl -s http://127.0.0.1:8190/status/main | grep -o '"doubt"' | head -1
# ⑥ 回魂注入有解读段（发一条消息后）
tail -5 /tmp/glue-hook-debug.log
# ⑦ 总线在动（尾部时间戳是当前，sandglass.entry 在涨）
tail -2 iso-sand/data/event_bus.jsonl
# ⑧ 配置中心一致性
bash stack_ctl.sh doctor
```

**判读（10 分钟版）：** ①⑥⑧ 绿 + ②③④⑤⑦ 任一红 → 系统降级运行；④ 红但 ③ 绿 = 生产 LMS 还是旧代码（见 §5 坑 16），重启 8190 即好；⑤ 红 = 体验层 D 未生效或旧代码；⑦ 里 `sandglass.entry` 不涨 = P0-3 链路断（查 `SANDGLASS_BUS_FILE` 推导）。

---

## 4. 运行时数据流（一篇文章的完整旅程）

以"dandan 在编辑器发一条消息"为例，数据每一步在哪、经过谁：

| 步 | 事件 | 数据在哪 | 经过谁 | 明/暗 |
|----|------|----------|--------|-------|
| 1 | dandan 发消息 | 编辑器前端 → WebSocket | **轻如烟编辑器** `edit-web.py` `inject_via_websocket`（:18888） | 入口 |
| 2 | **落沙（明线第一步）** | `sandglass.txt` 追加 1 行 `ts\|sender\|text` | `_sandglass_log`（⚠️当前截断 `content[:500]`）→ `sandglass_log_wrapper.py` → `sandglass_log.log_message`（文件锁+追加+shadow_sand 索引+织线三元组，仅 sender=user 触发织线） | 明线 |
| 3 | OpenClaw 收到消息，触发插件 hook | 插件内存 → HTTP | **glue-memory-injector** `before_prompt_build`（心跳轮跳过）→ `memory-recall.js` | 胶水 |
| 4 | **读侧融合检索** | glue 服务端 → 三后端 | **glue :19000** `POST /recall`：沙漏 txt（vault 三层检索）+ 向量 bge-m3（:11435）+ LMS 激活（:8190）→ 按 0.3/0.5/0.2 加权融合；同时 `POST /soul` 取 LMS 自述+状态+沙漏最近 2 条 | 明线→胶水 |
| 5 | **注入送回对话** | prompt 头部 `[回魂]`+`[记忆注入]` | 插件把结果拼成 `prependContext`（≤1500 字）→ OpenClaw 拼进模型调用 | 胶水→AI |
| 6 | AI 思考并回复 | LLM 输出 | OpenClaw → 主模型（deepseek） | 宿主 |
| 7 | **暗线塑形（每轮）** | LMS 状态（轮次+1、熵/惊讶/目的更新、J矩阵更新；体验层D：置信度场更新） | AI 每轮调 MCP `lms_store`/`store_memory` → LMS `process_turn`（编码→FEP 推断→学习→熵管理→目的调整（coherence 低时**强化已关注维度**，体验层C）→记忆更新与巩固（含反流畅项 ×(1−rebuttal_rate)×source_trust，体验层D）→检索→解码）——**当前这条线绕过胶水和总线（旁路）** | 暗线 |
| 8 | 总线事件 → LMS 塑形素材 | event_bus.jsonl → LMS `/feed`（限流 10 次/分钟） | **LmsFeedHandler** 订阅 `interfaces.store/task_complete/milestone/doubt.episode/sandglass.entry` → `POST :8190/feed`（503/超时指数退避重试，`LMS_FEED_RETRIES` 逃生门）；**P0-3 已接通：沙漏落沙流水经 `sandglass.entry` 喂塑形**（2026-08-11 实测 operation_log 出现 `LMS 塑形喂入成功 … source=sandglass`） | 总线→暗线 |
| 9 | **做梦巩固（空闲时）** | LMS 内部 | `DreamScheduler` 后台线程：记忆回放、SHY 衰减、吸引子景观漂移、目的演化；**体验层D 起含 `doubt_review` 阶段**（labile 裁决/低置信复核/反教条抽查，报告进 dream_state.json → [梦醒] 消息）；每次做梦发 `lms.dream_complete` 总线事件 | 暗线 |
| 10 | **自主唤醒（每 10min）** | 指标/告警/唤醒 | `pulse-cron.sh` → `self_pulse_cli.py`（读 LMS `/status` 写 `metrics.jsonl`；漂移则写 sandglass ⚠️ + 总线 anomaly）→ 显著事件过 `salience_gate`（显著性）→ `sleep_pressure`（体力/防自激）→ `wake_client` `POST :10554/hooks/wake` 唤醒主 AI | 唤醒 |
| 11 | **监督（周期）** | 审计/怀疑记录 | 玄鉴 5min 巡检 operation_log → `daemon_audit.log`，连续 FAIL 触发 doubt_hook；夜巡 23:30 汇总当天 → 隔离子代理旁观 → findings 写沙漏（tag=旁观者-警讯）→ 反教条复核 top10 高频记忆 | 监督 |
| 12 | **回魂注入（下一次对话）** | 下一轮 prompt | 步骤 3-5 循环：`/react`（解读段）+ `/soul`（把"最近的自己"自述+状态+最近记忆带回对话）→ AI 醒来知道自己是谁、大脑此刻什么感受 | 明线+暗线合流 |

**两条写侧路径的现状（重要，别搞混）：**
- **路径 A（实际发生）**：编辑器直写 sandglass.txt（明线）+ AI 每轮 MCP 直连 LMS（暗线）——两条旁路，**都绕过了胶水 /store 和总线**。
- **路径 B（设计正路，从未发生）**：对话 → glue `/store`（聚合写沙漏+LMS+向量）→ 总线 `interfaces.store` → LmsFeedHandler → LMS /feed。实测 glue `/store` 累计 **0 次调用**、`interfaces.store` 生产事件 **0 条**（仅 8/4 测试 5 条）。

---

## 5. 最容易踩的坑（按杀伤力排序）

1. **沙漏被遗忘（部署者的头号错误）**：只看 LMS 文档就以为系统完整。**沙漏是明线保底，没有它：没有流水账、没有回魂"最近"、没有叙事层、AI 失忆后无法找回自己。** 部署顺序第一步永远是沙漏。
2. **LMS `.env` 未 source**：LMS 启动前必须 `set -a; . ./.env; set +a`。不 source 会**静默降级**（embed 变 simple、LLM 不启用、`/health` 却显示正常）——"部署了但没生效"的头号元凶。
3. **`LMS_EMBEDDER` 不是 cloud / 向量服务不可达**：HF 在本机不可达，必须 `LMS_EMBEDDER=cloud` + `LMS_CLOUD_EMBED_URL=http://192.168.0.103:11435/v1/embeddings`（手机 Ollama bge-m3）。嵌入挂了 → LMS 与胶水向量全部降级。
4. **双写（2026-08-11 已修，P0-1）**：落沙幂等去重（`SANDGLASS_DEDUP_WINDOW`，同 sender+text 时间窗内只写一次）。修复前每条消息落沙 ×2；修复后新行应无重复。**新环境若把去重窗口调成 0 或换回旧 sandglass_log，双写复发。**
5. **sender 错标（2026-08-11 已修，P0-2）**：`SANDGLASS_SENDER_MAP` 默认 `{"sister":"user"}` 归一化（sister→user），织线三元组提取恢复。**新环境注意：新 sender 名要加进 SANDGLASS_SENDER_MAP，否则织线又停摆。**
6. **500 字截断（2026-08-11 已修，P0-2）**：落沙正文不再截断（`SANDGLASS_MAX_TEXT_LEN` 默认 0=不截断；旧版 `content[:500]` 会丢长消息后半）。**新环境若把它设成小值，长消息又丢尾。**
7. **总线心跳 ≠ 沙漏数据**：`event_bus.jsonl` 里 1789 条 `sandglass.heartbeat` 全是**调度器存活心跳**（`deploy/heartbeat.py` 发布，误导命名），不代表沙漏活着、也不是沙漏数据。判断沙漏活着只能看 `sandglass.txt` mtime/行数，别看总线。
8. **`LMS_FEED_ENABLED` 开关被关**：这是"总线→LMS /feed 塑形"的总开关（默认开；env.local 不设=1）。关掉后 LMS 收不到任何总线塑形素材，暗线断粮但不报错。
9. **沙漏流水→LMS 塑形素材（2026-08-11 已接通，P0-3）**：落沙成功后发 `sandglass.entry` 总线事件，consumer 的 LmsFeedHandler 已订阅（source=sandglass，跳过心跳噪声过滤）→ LMS /feed。**验证方式**：`grep -c "sandglass.entry" event_bus.jsonl` 在涨 + operation_log 出现 `LMS 塑形喂入成功 … text_len=…`。**新环境若 SANDGLASS_BUS_FILE 推导失败（找不到 Agent OS/iso-sand/data），此链路静默断**（落沙正常但不发事件，不报错）。LMS→沙漏标记方向仍未实现（P2-1）。
10. **读侧超时静默失败（已修，但部署者易复犯）**：插件 HTTP 超时从 4000ms 提到 15000ms（glue 也从单线程改 `ThreadingHTTPServer`，`/recall` 从 7-10s 降到 1.15s）。**新环境若改小超时或改回单线程，记忆注入会全部静默 MISS，AI 表现为"失忆"但不报错。**
11. **心跳轮注入会弄坏会话（已修，别"修回去"）**：8/7 曾因心跳轮也注入导致 `openclaw:prompt-error` 会话带伤。插件现在双重判据跳过心跳（`ctx.trigger==="heartbeat"` 或 prompt 含 heartbeat poll）。**不要**在插件里去掉这个判断。
12. **沙漏权威源是 txt 不是 SQLite**：`sandglass.txt`（4765 行）是权威源；SQLite 辅助库（906 条）只作索引，落后 2305+ 条且有写锁冲突。胶水层读侧必须走 `sandglass_vault_adapter`（直接复用 vault 读 txt），**不要**用 SQLite adapter 当权威。
13. **绝对路径硬编码**：所有绝对路径只允许出现在 `Agent OS/env.local`（A 节 8 个路径）；脚本要么读它、要么相对推导。新机器只改 env.local，**不要**在脚本里 sed 路径。
14. **`/vol1` 与 `/vol2` 是同一文件**：`/vol1/轻如烟/轻如烟` 与 `/vol2/1000/AI专用/所有自动化/轻如烟` 是 bind mount（inode 相同）。不要在两者间"复制同步"——会破坏文件锁与索引。
15. **glue `/store` 聚合写从未被调用**：写侧实际走编辑器直写 + MCP 直连两条旁路。设计正路（glue /store → interfaces.store → feed）从未发生。想接暗线塑形素材，P0-3（落沙发 sandglass.entry）已落地为当前正路，P2-2（统一走 glue /store）二选一，别两条都改。
16. **生产 8190 跑旧代码（体验层最常见的"部署了但没生效"）**：代码改了、测试过了，但 `:8190` 没重启 → `/react` 404 / 无 `doubt` 字段 / 回魂无解读段，且**不报错**（glue /react 会 502 fail-open，插件优雅降级成旧行为）。部署新代码后必须重启：`set -a; . ./.env; set +a` + 重启 8190。同理插件 memory-recall.js 改后必须**重载 OpenClaw gateway 插件**才生效（不改则仍是旧两路并行）。
17. **子代理样板污染 [记忆注入]**（2026-08-11 已修，体验层B）：`_GARBAGE_TEXT_RE` 纯增量 +6 条正则（`[Subagent Context]`/`You are running as a subagent`/`[Subagent Task]`/`HEARTBEAT_OK`/`Results auto-announce`/`Your assigned task is in the sy`），入口过滤防新增。**新环境注意：新调度样板串出现时往正则里加，勿删现有 4 条。**
18. **SIGUSR1 不重载插件**：改完 OpenClaw 插件（memory-recall.js/index.js）发 SIGUSR1 无效——插件代码要 **gateway 完全重启**才加载；且 SIGUSR1 **禁止连击**（第二次在活跃会话中 = forced restart = 杀 session）。SIGUSR1 前确认 session 空闲（无 pending 模型调用）。
19. **4:00 会话重置已永久关闭**：openclaw.json 已设 `session.reset: {mode: idle, idleMinutes: 999999}`（备份 `.bak-20260811-0119-session-reset`，2026-08-11 生效）。**不要改回去**——每日 4:00 重置是历史失忆感元凶之一；现在由 `session-reset-watchdog`（cron `*/2`）守护归档被重置会话。
20. **查询污染召回（2026-08-11 已修，召回 L1）**：插件曾把含 untrusted metadata 的完整提示词（Sender 块/时间戳/Subagent 模板）当检索 query → 注入全是编辑器模板记忆。已修三层：插件复刻 `stripInboundMetadata` 净化（L1-a）+ `ctx.sessionKey` 识别子代理轮跳过（L1-b）+ glue `/recall` 入口 `purify_recall_query` 兜底（L1-c）。**新环境注意：glue 侧已生效；插件侧需 gateway 重载才生效（改完重启，见坑 18）**。

---

## 6. 明暗双线故障判定（3 分钟巡检法，给不懂代码的人）

> 只看 4 个文件/接口，3 分钟判断系统死活。**核心心法：明线看 txt 在不在涨，暗线看轮次在不在涨，胶水看注入日志，总线看 jsonl 尾部。**

```bash
# 60 秒内跑完（一条命令全看）：
cd "Agent OS"
bash status_all.sh                                   # ① 6 服务全绿？
tail -3 "所有自动化/轻如烟/sandglass/sandglass.txt"   # ② 明线：txt 尾部是今天的对话？
curl -s http://127.0.0.1:8190/status/main | head -c 300   # ③ 暗线：turn_count 在涨？熵/惊讶/目的非零？
tail -3 iso-sand/data/event_bus.jsonl                # ④ 总线：尾部时间戳是当前？（lms.plastified 约 5min 一条）
tail -3 /tmp/glue-hook-debug.log                     # ⑤ 胶水：最近对话有 INJECTED？（没有=读侧断）
```

**判定表：**

| 症状 | 判定 | 下一步 |
|------|------|--------|
| ① 全绿 + ② txt 在涨 + ③ 轮次在涨 + ⑤ 有 INJECTED | ✅ **系统活着**，明暗双线+胶水全通 | 不用动；可选看 ④ 总线确认怀疑闭环 |
| ② txt 不涨（mtime 旧/无今天内容） | ❌ **明线断了**（最严重，失忆根源） | 查编辑器 :18888 是否在跑；发条消息看 `tail -5 sandglass.txt`；查 `_sandglass_log` 的 wrapper 是否存在 |
| ② txt 在涨但 ③ 轮次不涨 | ⚠️ **暗线断**（LMS 没收到对话） | `curl :8190/health`；查 MCP lms_store 是否注册；查 `.env` 是否 source（/status 返回空=降级） |
| ③ 在涨但 ⑤ 无 INJECTED | ⚠️ **读侧断**（记忆没送回对话=AI 失忆） | 查 glue :19000 health backends；`tail -50 /tmp/glue-hook-debug.log` 看 MISS reason（超时/网络/限流） |
| ④ event_bus.jsonl 尾部是几小时前 | ⚠️ **总线/调度器断** | 查 scheduler.pid/consumer.pid；看 `iso-sand/data/operation_log.jsonl` 尾部 |
| ① 某服务 ❌ | ❌ 该服务死了 | `bash start_all.sh` 重启（幂等）；单服务看 `Agent OS/logs/<svc>.log` |

**深入判据（30 秒补充）：**
- **明线质量**：`grep -c "今天的关键词" sandglass.txt` 应为 1（P0-1 去重生效后=1；若=2 查 `SANDGLASS_DEDUP_WINDOW`）；`grep "| user |" sandglass.txt | tail -1` 应为今天（sender 错标则织线停摆）。
- **体验层质量**：`curl :8190/react` 有 `interpretation`；`/status/main` 有 `doubt` 字段（体验层D）；插件日志有 `INJECTED-light`（限流轻量注入在工作）。
- **暗线质量**：`grep -c "producer=lms.feed" iso-sand/data/operation_log.jsonl` 在涨（text_len>20 的是真实素材；`sandglass.entry` 来源的即沙漏流水）；LMS `/feed` 计数看 `Agent OS/logs/lms_api.log`。
- **监督活着**：`ls -la workspace/logs/night_patrol.last_run`（应为昨天 23:30 后）；`tail -3 同构沙盘/data/daemon_audit.log` 是今天的。

---

## 附：本文件与 TOPOLOGY.md 的边界

- **TOPOLOGY.md** = 模块视角（组件/端口/仓库/契约表/文件地图）——"系统有哪些零件、每个零件在哪"。
- **SYSTEM.md**（本文件） = 数据流视角（明暗双线/部署顺序/运行时旅程/坑/巡检）——"零件怎么咬合、怎么装、怎么判断活着"。
- **SYSTEM_HEALTH.md** = 全系统健康巡检手册（自动化版）——"怎么知道它活着/坏了"：`bash scripts/system_health_check.sh` 一条命令全检，cron 每 30min 自动巡检、状态变化才告警。**日常查健康先看它。**
- **部署前必读顺序**：SYSTEM.md → TOPOLOGY.md → 各模块 README。任何陌生 AI 按此顺序读完即可完整部署，不会漏掉沙漏。
- 维护规则：改端口/布局/仓库 → 同步改 TOPOLOGY.md；改数据流/部署顺序/新增坑 → 同步改本文件；改巡检项/阈值 → 同步改 SYSTEM_HEALTH.md + scripts/system_health_check.sh。

---
*事实来源：沙漏链路诊断-20260810.md（四层架构/双写/sender/feed 计数）、NexSandglass README+ARCHITECTURE+PATCH-README（P0-1/2/3）、LMS README+docs/ARCHITECTURE.md+docs/体验层实施-20260811.md、体验层总设计-20260811.md v1.1（/react/解读段/过滤/元目的翻转/置信度场）、memory-integration-layer README+interfaces/README、Agent OS TOPOLOGY/env.local/start_all.sh/status_all.sh/DEPLOY-GLOBAL/DOUBT-SYSTEM/iso-sand handlers.py+event_schema.yaml、轻如烟 SELF_PULSE_README+pulse-cron.sh+self_pulse_cli.py（WAKE_CHANNEL）+salience_gate.py（SG_DREAM_FEED/SG_DOUBT_FEED）+wake_client.py+sleep_pressure.py、glue-memory-injector index.js+memory-recall.js+openclaw.plugin.json、edit-web.py、sandglass_http_api.py、sandglass_log.py（SANDGLASS_*）。2026-08-11 实测：8190/19000 均已跑体验层新代码（/react 200），event_bus 含 61 条 sandglass.entry 且 operation_log 有 sandglass 来源的 feed 成功记录。待核实项：决策粒子原调用方（P1-2）。*

## 6. 设计遗产（明确不修，2026-08-10 标注）

| 模块 | 状态 | 理由 |
|------|------|------|
| **L3 画像（persona 蒸馏）** | 🗄️ 遗产 | 职责与 LMS 目的层重叠；LMS 是 FEP 框架（有理论依据），画像维护 6/16 后停摆，无调用方。需要"人类可读自我描述"时再议 |
| **L4 决策粒子（决策追踪/偏移率/幽灵决策）** | 🗄️ 遗产 | 全库仅 1 条、feed_all 零调用方、从未接入链路、历史上无深入讨论。决策追踪职责由 **LMS 目的层 precision 调整**承担，是旧方案的影子，修的成本>收益 |

> 判定依据：《沙漏链路诊断-20260810.md》+ 沙漏搜索实证（2026-08-10 23:08 dandan 确认：画像/L4 没必要修）

---

## 7. 成果存档速览（2026-08-11/12 增量，完整版见 `成果存档索引-20260812.md`）

> 完整清单（标题/文档路径/状态/一句话说明）在 `成果存档索引-20260812.md`（本仓库，2026-08-12 建立）。本节只列状态，防止 SYSTEM.md 膨胀。

| 成果 | 状态（2026-08-12 01:30） | 关键文档 |
|------|--------------------------|----------|
| 提取层+双向塑形 v1.3 设计（非生成式为主+LLM 增强） | 🔄 设计完成，待审计 v3/实施（三阶段） | 提取层双向塑形-v1.3设计-20260812.md |
| 惊讶度修复闭环（surprise −36→+11，语义拆分） | ✅ 已闭环（LMS C1-C5 + glue G1，693 passed） | 惊讶度修复-进度.md |
| 体验层 A-D（/react、回魂三段式、置信度场、元目的翻转） | ✅ A-D 已上线（总设计 v1.1 待 dandan 确认实施启动项） | 体验层总设计-20260811.md |
| 失忆根因三件套（FTS 冻结/ts 列/搜索工具） | ✅ 已修复（3 项 4 commit，FTS 重建 984 去重条目） | workspace/memory/2026-08-11.md |
| CONTRACTS.yaml 契约层 + 玄鉴 push_verify | ✅ 已建立（审计有条件通过，3 必修复项：SG-05 回填/cron 接入/推送积压） | CONTRACTS.yaml + 契约层审计-20260811.md |
| 梦醒回路阶段 1+2（WAKE_CHANNEL=b 夜间观测） | ✅ 已实施（审计有条件通过）→ 🌙 夜间观测待进行 | 梦醒回路-阶段2审计-20260811.md |
| 召回 L1 修复（query 净化） | ✅ 已实施（glue 生效；插件待 gateway 重载生效） | 召回L1实施审计-20260811.md |
| 方法论 v1.1（system_health_check.sh 审计前置基线） | ✅ 已落地（dandan 钦定进方法论） | 子AI调度方法论-v1.0.md（内容 v1.1） |
| 丰碑对齐调研（磨损机制铺路） | ✅ 调研完成（铺路，非实施；磨损生态从未接线=孤儿模块） | 丰碑LMS对齐调研-20260812.md |
