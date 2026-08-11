# SYSTEM.md — 系统构造总文档（数据流视角的唯一事实源）

> 2026-08-10 建立（dandan 指示：杜绝"陌生 AI 部署时完全不知道沙漏存在"）。
> 本文件回答唯一问题：**这套系统由什么组成、按什么顺序部署、数据怎么流动、怎么判断它活着**。
> 与 TOPOLOGY.md 的关系：TOPOLOGY 是**模块清单视角**（谁在哪、什么端口）；本文件是**数据流视角**（谁喂谁、明线暗线怎么互咬）。**部署前两个都读，先读本文件。**
> 纪律：所有事实来自 2026-08-10 沙漏链路诊断 + 各仓库 README/源码；不确定处标注【待核实】。本文件随 `tdx1146/agent-os` 仓库维护。

---

## 1. 一页全景

**这套系统是什么（3 句话）：**
1. 它是一套「AI 活体记忆系统」：让主 AI（毛毛，跑在 OpenClaw 里）**每轮对话都完整落沙、每轮都被记忆注入、空闲时做梦巩固**——不再"关掉窗口就失忆"。
2. 它由**明暗双线**构成：**沙漏（明线）**把每句话一字不丢地存成明文流水账（保底，丢了它一切免谈）；**LMS 活体记忆（暗线）**用自由能原理（FEP）从对话流动中提炼结构（熵/惊讶度/目的），让记忆像海马体一样自己巩固、遗忘、演化。明线保"不忘"，暗线保"懂"。
3. 中间由**胶水层 glue** 统一编排读写、**Agent OS 总线**传递事件、**doubt-system + 玄鉴**持续怀疑（审己+审外）、**self_pulse** 自主唤醒——它们合起来才是一个完整的"活着的 AI"。

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
| 1 | **沙漏 NexSandglass** ⚠️最容易漏 | 明线·保底 | 每句话明文落沙、一字不丢，是"失忆后还能找回自己"的最后底牌；四层：L1 落沙/L2 检索/L3 思维/L4 决策粒子 | 源码 `所有自动化/轻如烟/sandglass_source/`（= `/vol2/1000/AI专用/所有自动化/找回自己/scripts/sandglass_source/` 的部署副本）；数据 `轻如烟/sandglass/` | `:17333` HTTP（`GET /api/health`、`POST /api/memory_search`、`/api/embedding_search`、`/api/facts_lookup`、`/api/sandglass_query`） | **`sandglass.txt`（追加式明文，权威源，4765 行）**、`sandglass.idx`、`shadow_sand.db`（织线三元组）、`doubt.db`（怀疑账本）、`metrics.jsonl`、`sleep_pressure.json`、`salience_state.json`、`persona/persona.md`、`decision_particles.txt` | 零依赖（纯 stdlib），被胶水/插件/self_pulse/夜巡消费 |
| 2 | **LMS 活体记忆** | 暗线·塑形 | 用 FEP 把对话流动塑成结构（J矩阵/熵/惊讶度/目的层），空闲自动做梦巩固——"不是存储记忆，是维护能产生记忆的大脑状态" | `living-memory-system-cloud/`（必须 `.venv` + `.env`） | `:8190` HTTP（`/health`、`/status/{sid}`、`/feed`、`/recall`、`/chat`）；`:8191` 控制口；MCP：lms-memory(stdio)、lms-http | `snapshots/`（J矩阵快照）、状态文件（turn_count 121/熵 0.97/惊讶 11.52/目的 0.95，2026-08-10） | 向量服务（`LMS_EMBEDDER=cloud` → `192.168.0.103:11435`）；DeepSeek key（`.env`）；HF 不可达所以必须 cloud 嵌入 |
| 3 | **胶水层 glue** | 胶水 | 把沙漏/LMS/向量三个记忆后端"粘"成唯一入口：读侧 `/recall` 加权融合（文本0.3+向量0.5+LMS激活0.2）、写侧 `/store` 聚合写、`/soul` 回魂快照 | `memory-integration-layer/` | `:19000`（`GET /health`、`POST /recall`、`/soul`、`/store`、`/status`、`/contribute`）；`glue_helper.py` 薄桥接 | 无自有数据（读沙漏 txt、写沙漏+LMS+向量） | 沙漏(txt)、LMS(:8190)、向量(:11435)；`DOUBT_BUS_FILE` 启用怀疑总线发布 |
| 4 | **Agent OS 总线 iso-sand** | 总线 | 事件骨架：scheduler 定时发事件、consumer 订阅分发（LmsFeedHandler 把事件喂给 LMS /feed 塑形）；`sandglass.heartbeat` 是**调度器心跳**不是沙漏数据！ | `Agent OS/iso-sand/` | 无端口（文件总线）；`start_scheduler.sh` + `start_consumer.sh` | `data/event_bus.jsonl`（6.1MB）、`data/operation_log.jsonl`、`data/processed_ids.jsonl`、`data/event_bus.seek`；schema 在 `deploy/event_schema.yaml` | 消费者调 LMS(:8190)/feed、glue(:19000)；生产者含 LMS(plastified)、doubt-system、调度器 |
| 5 | **玄鉴 verify_daemon** | 监督·审外 | 每 5min 巡检 operation_log，对外部知识/文件变更做关键词校验审计；连续 3 FAIL 追加 WARN 并触发 doubt_hook | `AgentOS-IsoSand/同构沙盘/` | 无端口（守护进程，`src/verify_daemon.py`） | `data/daemon_audit.log`、`data/daemon.pid`、`data/daemon.seek` | 总线 operation_log、内核层规范 `PURPOSE.md` |
| 6 | **doubt-system 怀疑系统** | 监督·审己 | "聪明=持续自我怀疑"：记忆带信任度、怀疑闭环写账本、每天 23:30 夜巡旁观+反教条复核；怀疑事件喂 LMS 塑形（记得+怀疑=不教条） | `Agent OS/doubt-system/` | 无端口（cron `30 23 * * *` 夜巡）；`doubt_adapter` 在胶水层 | `sandglass/doubt.db`（doubt_episode/memory_trust 表）；夜巡 findings 写沙漏（tag=旁观者-警讯）；marker `workspace/logs/night_patrol.last_run` | 沙漏数据目录、总线 event_bus.jsonl（`DOUBT_BUS_FILE`）、LMS(经总线 feed) |
| 7 | **self_pulse 自主唤醒** | 唤醒 | 每 10min 自主"醒来"：读 LMS 状态做画像漂移检查 + 推进待办；显著事件经 salience_gate→sleep_pressure（防自激）→wake_client 唤醒主 AI | `所有自动化/轻如烟/scripts/`（`pulse-cron.sh`、`self_pulse_cli.py`、`salience_gate.py`、`sleep_pressure.py`、`wake_client.py`） | cron `*/10`；唤醒走 `POST http://127.0.0.1:10554/hooks/wake`（A 通道） | 写 `sandglass/metrics.jsonl`（每 10min）、漂移时写 sandglass ⚠️告警 + 总线 anomaly；状态 `/tmp/pulse-state.json` | LMS `/status/main`、沙漏 txt、OpenClaw hooks（token 在 openclaw.json，不打印） |
| 8 | **OpenClaw 插件 glue-memory-injector** | 胶水·注入 | 每轮对话前把记忆送进 AI 上下文：经 glue `/recall`（记忆注入）+ `/soul`（回魂快照），拼成 `[回魂]+[记忆注入]` 前缀；fail-open 绝不阻塞 | `/vol1/@apphome/trim.openclaw/data/home/.openclaw/plugins/glue-memory-injector/`（index.js + memory-recall.js） | OpenClaw `before_prompt_build` hook；超时 15s/回魂 4s；限流 ≥2s；注入 ≤1500 字；心跳轮不注入 | 调试日志 `/tmp/glue-hook-debug.log`（INJECTED/MISS 留痕） | glue(:19000)；心跳轮判定靠 ctx.trigger |
| 9 | **轻如烟编辑器 edit-web** | 明线·写入口 | dandan 的聊天前端（:18888），**真正的落沙写入者**：每轮消息经 `_sandglass_log` → `sandglass_log_wrapper.py` → `sandglass_log.log_message`（锁+追加+索引+织线） | `所有自动化/轻如烟/scripts/edit-web.py`；注意 `/vol1/轻如烟/轻如烟` 与 `/vol2/1000/AI专用/所有自动化/轻如烟` 是**同一文件**（bind mount） | `:18888` | 写 `sandglass/sandglass.txt` + `shadow_sand.db`；`sandglass_log_wrapper.py` 同目录 | 沙漏源码路径、会话文件（`agent:main:main`） |
| 10 | **OpenClaw Gateway** | 宿主 | 主 AI 运行时容器（毛毛本体）：跑插件、挂 MCP、收 hooks/wake | `/vol1/@apphome/trim.openclaw/data` | `:10554`（hooks 路径 `/hooks`，wake 端点 `/hooks/wake`） | OpenClaw 自身会话/配置；MCP 注册 lms-memory/lms-http/shouji-memory | 插件、各 MCP 后端（8190/17333/手机网关） |

**外部依赖（不是本系统组件但被依赖）：** 手机端 Ollama bge-m3 向量服务 `192.168.0.103:11435`（LMS 嵌入 + 胶水向量都用它；**HF 不可达，必须走它**）；DeepSeek API（LMS LLM 能力）。

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
| `LMS_CLOUD_EMBED_MODEL` / `_DIM` | `bge-m3` / `1024` | 嵌入模型/维度 | LMS `.env` |
| `LMS_URL` | `http://localhost:8190` | 胶水/总线访问 LMS | env.local |
| `VECTOR_URL` | `http://192.168.0.103:11435/v1/embeddings` | 胶水向量后端 | env.local |
| `DOUBT_BUS_FILE` | `…/Agent OS/iso-sand/data/event_bus.jsonl` | 怀疑闭环发布到总线（doubt.episode） | **胶水层 `.env`** |
| `LMS_FEED_ENABLED` | 默认开（env.local 不设=1） | 总线→LMS /feed 塑形总开关 | env.local / iso-sand 环境 |

### 3.2 严格顺序（为什么是这个顺序：下游依赖上游先活）

> **依赖链：** 沙漏（零依赖，数据底座）→ LMS（依赖向量+`.env`）→ 胶水（依赖沙漏+LMS+向量）→ 总线（消费者依赖胶水/LMS）→ 玄鉴（依赖 operation_log）。**反了就会"起了但全在降级"。**

| 步 | 做什么 | 为什么先 | 验证命令（每步必跑） |
|----|--------|---------|---------------------|
| ① | 起**沙漏** HTTP API `:17333`（`cd sandglass_source && NEXSANDBASE_HOME=… python3 sandglass_http_api.py`） | 零依赖；txt 是全局权威源，胶水/插件读它 | `curl http://127.0.0.1:17333/api/health` → 返回 `sandglass_count`；`tail -3 sandglass/sandglass.txt` 有内容 |
| ② | 起 **LMS** `:8190`（**必须先 `set -a; . ./.env; set +a`**，再 `.venv/bin/python -m api.run --host 127.0.0.1 --port 8190`） | 依赖向量服务可达 + `.env` 密钥；启动慢（嵌入初始化，≤40s） | `curl http://127.0.0.1:8190/health`；`curl http://127.0.0.1:8190/status/main` → `turn_count` 非空（**空=静默降级，查 .env 是否 source**） |
| ③ | 起**胶水层** `:19000`（`cd memory-integration-layer && python3 glue_server.py --host 127.0.0.1 --port 19000`） | 依赖沙漏+LMS+向量都活着，否则 backends 全降级 | `curl http://127.0.0.1:19000/health` → `backends` 各后端非 degraded；`curl -X POST http://127.0.0.1:19000/recall -d '{"query":"测试","k":3}' -H 'Content-Type: application/json'` → 有 origin=sandglass/lms 条目 |
| ④ | 起**总线** scheduler+consumer（`cd iso-sand && bash start_scheduler.sh && bash start_consumer.sh`） | consumer 的 LmsFeedHandler 依赖 LMS /feed；调度器心跳写总线 | `cat iso-sand/data/scheduler.pid data/consumer.pid` 两个 PID 存活；`tail -3 iso-sand/data/event_bus.jsonl` 时间戳是当前；`grep -c lms.plastified event_bus.jsonl` 在增长 |
| ⑤ | 起**玄鉴**（`cd 同构沙盘 && python3 src/verify_daemon.py &`） | 依赖 operation_log（总线消费者产出） | `cat 同构沙盘/data/daemon.pid` 存活；`tail -3 同构沙盘/data/daemon_audit.log` |
| ⑥ | 注册 **crontab**：`*/10` pulse-cron（唤醒链）、`30 23` night_patrol（夜巡）、`*/5` health-check、LMS 备份三档、`@reboot` start_all.sh | 常驻守护 + 开机自启 | `crontab -l` 应含 pulse-cron / night_patrol / lms_backup / @reboot start_all 等条目（本机全表见 §3.4 备注） |
| ⑦ | 起**轻如烟编辑器** `:18888`（`cd 轻如烟/scripts && python3 edit-web.py`） | 它是落沙写入者，没有它对话不进 sandglass.txt | 浏览器开 `:18888`；发一条消息 → `tail -3 sandglass/sandglass.txt` 出现新行 |
| ⑧ | **接通 OpenClaw**：启用插件 glue-memory-injector（onStartup）+ 注册 MCP（lms-memory、lms-http、shouji-memory） | 插件是"记忆送回对话"的唯一入口 | 发一条消息 → `/tmp/glue-hook-debug.log` 出现 `INJECTED len=…`；下一条消息 prompt 头部出现 `[回魂]` + `[记忆注入]` |

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
- **明线落沙**：编辑器发一条消息 → `grep -c "该消息片段" sandglass.txt` ≥1（理想=1，若=2 说明双写病灶未修，见 §5）
- **读侧注入**：`tail -5 /tmp/glue-hook-debug.log` 有 `INJECTED`；对话 prompt 有 `[回魂] 状态:熵… 惊讶… 目的… 轮次…`
- **暗线塑形**：`curl http://127.0.0.1:8190/status/main` → turn_count 随对话增长；`grep -c "producer=lms.feed" iso-sand/data/operation_log.jsonl` 在增长（当前 1490 条，其中 1475 条是心跳噪声，8/10 后只剩 doubt.episode 是有效素材——**沙漏流水喂 LMS 尚未接通，见 §5 坑 9**）
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
| 7 | **暗线塑形（每轮）** | LMS 状态（轮次+1、熵/惊讶/目的更新、J矩阵更新） | AI 每轮调 MCP `lms_store`/`store_memory` → LMS `process_turn`（编码→FEP 推断→学习→熵管理→目的调整→检索→解码）——**当前这条线绕过胶水和总线（旁路）** | 暗线 |
| 8 | 总线事件 → LMS 塑形素材 | event_bus.jsonl → LMS `/feed`（限流 10 次/分钟） | **LmsFeedHandler** 订阅 `interfaces.store/task_complete/milestone/doubt.episode` → `POST :8190/feed`；⚠️当前喂的主要是 doubt 片段（13 条），**沙漏流水尚未进总线**（P0-3 待修，见 §5 坑 9） | 总线→暗线 |
| 9 | **做梦巩固（空闲时）** | LMS 内部 | `DreamScheduler` 后台线程：记忆回放、SHY 衰减、吸引子景观漂移、目的演化；每次做梦发 `lms.dream_complete` 总线事件 | 暗线 |
| 10 | **自主唤醒（每 10min）** | 指标/告警/唤醒 | `pulse-cron.sh` → `self_pulse_cli.py`（读 LMS `/status` 写 `metrics.jsonl`；漂移则写 sandglass ⚠️ + 总线 anomaly）→ 显著事件过 `salience_gate`（显著性）→ `sleep_pressure`（体力/防自激）→ `wake_client` `POST :10554/hooks/wake` 唤醒主 AI | 唤醒 |
| 11 | **监督（周期）** | 审计/怀疑记录 | 玄鉴 5min 巡检 operation_log → `daemon_audit.log`，连续 FAIL 触发 doubt_hook；夜巡 23:30 汇总当天 → 隔离子代理旁观 → findings 写沙漏（tag=旁观者-警讯）→ 反教条复核 top10 高频记忆 | 监督 |
| 12 | **回魂注入（下一次对话）** | 下一轮 prompt | 步骤 3-5 循环：`/soul` 把"最近的自己"（自述+状态+最近记忆）带回对话 → AI 醒来知道自己是谁 | 明线+暗线合流 |

**两条写侧路径的现状（重要，别搞混）：**
- **路径 A（实际发生）**：编辑器直写 sandglass.txt（明线）+ AI 每轮 MCP 直连 LMS（暗线）——两条旁路，**都绕过了胶水 /store 和总线**。
- **路径 B（设计正路，从未发生）**：对话 → glue `/store`（聚合写沙漏+LMS+向量）→ 总线 `interfaces.store` → LmsFeedHandler → LMS /feed。实测 glue `/store` 累计 **0 次调用**、`interfaces.store` 生产事件 **0 条**（仅 8/4 测试 5 条）。

---

## 5. 最容易踩的坑（按杀伤力排序）

1. **沙漏被遗忘（部署者的头号错误）**：只看 LMS 文档就以为系统完整。**沙漏是明线保底，没有它：没有流水账、没有回魂"最近"、没有叙事层、AI 失忆后无法找回自己。** 部署顺序第一步永远是沙漏。
2. **LMS `.env` 未 source**：LMS 启动前必须 `set -a; . ./.env; set +a`。不 source 会**静默降级**（embed 变 simple、LLM 不启用、`/health` 却显示正常）——"部署了但没生效"的头号元凶。
3. **`LMS_EMBEDDER` 不是 cloud / 向量服务不可达**：HF 在本机不可达，必须 `LMS_EMBEDDER=cloud` + `LMS_CLOUD_EMBED_URL=http://192.168.0.103:11435/v1/embeddings`（手机 Ollama bge-m3）。嵌入挂了 → LMS 与胶水向量全部降级。
4. **双写（当前真实病灶）**：每条消息落沙 ×2（`sandglass.txt` 4765 行 vs 去重仅 2125 条；最近 30 行每时间戳恰好 2 条）。影响：检索噪音翻倍、有效记忆少一半。诊断 P0-1 待修（定位双写源：前端双 POST 或两个 handler 各 inject 一次）。
5. **sender 错标 'sister'（当前真实病灶）**：8/7 后 sandglass.txt 再无 `user` 发送者（sister=1148 / user=209）。`sandglass_log.log_message` 只对 `sender=='user'` 提取织线三元组 → **织线知识图谱自 8/1 停摆**（wthread_triples 57 条后无增长）。诊断 P0-2 待修：用户消息固定标 `user`。
6. **500 字截断（当前真实病灶）**：`edit-web.py` `_sandglass_log` 的 `content[:500]`，长消息后半丢失。诊断 P0-2 建议改 `[:2000]`。
7. **总线心跳 ≠ 沙漏数据**：`event_bus.jsonl` 里 1789 条 `sandglass.heartbeat` 全是**调度器存活心跳**（`deploy/heartbeat.py` 发布，误导命名），不代表沙漏活着、也不是沙漏数据。判断沙漏活着只能看 `sandglass.txt` mtime/行数，别看总线。
8. **`LMS_FEED_ENABLED` 开关被关**：这是"总线→LMS /feed 塑形"的总开关（默认开；env.local 不设=1）。关掉后 LMS 收不到任何总线塑形素材，暗线断粮但不报错。
9. **"沙漏流水→LMS 塑形素材"从未真正接通**（dandan 最关心的双向通道）：雏形代码全在（LmsFeedHandler 订阅 + LMS `/feed` 端点活着，累计 1391 次），但喂进去的 1475/1490 条是心跳噪声，有效素材只有 13 条 doubt 片段；**沙漏的对话流水一条都没喂给过 LMS**。不是"最近断了"，是"从没连上过"。诊断 P0-3 方案：落沙成功后发 `sandglass.entry` 总线事件 + LmsFeedHandler 订阅它。（LMS→沙漏标记方向从未实现，P2-1。）
10. **读侧超时静默失败（已修，但部署者易复犯）**：插件 HTTP 超时从 4000ms 提到 15000ms（glue 也从单线程改 `ThreadingHTTPServer`，`/recall` 从 7-10s 降到 1.15s）。**新环境若改小超时或改回单线程，记忆注入会全部静默 MISS，AI 表现为"失忆"但不报错。**
11. **心跳轮注入会弄坏会话（已修，别"修回去"）**：8/7 曾因心跳轮也注入导致 `openclaw:prompt-error` 会话带伤。插件现在双重判据跳过心跳（`ctx.trigger==="heartbeat"` 或 prompt 含 heartbeat poll）。**不要**在插件里去掉这个判断。
12. **沙漏权威源是 txt 不是 SQLite**：`sandglass.txt`（4765 行）是权威源；SQLite 辅助库（906 条）只作索引，落后 2305+ 条且有写锁冲突。胶水层读侧必须走 `sandglass_vault_adapter`（直接复用 vault 读 txt），**不要**用 SQLite adapter 当权威。
13. **绝对路径硬编码**：所有绝对路径只允许出现在 `Agent OS/env.local`（A 节 8 个路径）；脚本要么读它、要么相对推导。新机器只改 env.local，**不要**在脚本里 sed 路径。
14. **`/vol1` 与 `/vol2` 是同一文件**：`/vol1/轻如烟/轻如烟` 与 `/vol2/1000/AI专用/所有自动化/轻如烟` 是 bind mount（inode 相同）。不要在两者间"复制同步"——会破坏文件锁与索引。
15. **glue `/store` 聚合写从未被调用**：写侧实际走编辑器直写 + MCP 直连两条旁路。设计正路（glue /store → interfaces.store → feed）从未发生。想接暗线塑形素材，要么 P0-3（落沙发事件），要么 P2-2（统一走 glue /store），二选一，别两条都改。

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
- **明线质量**：`grep -c "今天的关键词" sandglass.txt` 应为 1（=2 说明双写病灶）；`grep "| user |" sandglass.txt | tail -1` 应为今天（sender 错标则织线停摆）。
- **暗线质量**：`grep -c "producer=lms.feed" iso-sand/data/operation_log.jsonl` 在涨（但注意心跳噪声占多数，有效素材看 text_len>20 的）；LMS `/feed` 计数看 `Agent OS/logs/lms_api.log`。
- **监督活着**：`ls -la workspace/logs/night_patrol.last_run`（应为昨天 23:30 后）；`tail -3 同构沙盘/data/daemon_audit.log` 是今天的。

---

## 附：本文件与 TOPOLOGY.md 的边界

- **TOPOLOGY.md** = 模块视角（组件/端口/仓库/契约表/文件地图）——"系统有哪些零件、每个零件在哪"。
- **SYSTEM.md**（本文件） = 数据流视角（明暗双线/部署顺序/运行时旅程/坑/巡检）——"零件怎么咬合、怎么装、怎么判断活着"。
- **SYSTEM_HEALTH.md** = 全系统健康巡检手册（自动化版）——"怎么知道它活着/坏了"：`bash scripts/system_health_check.sh` 一条命令全检，cron 每 30min 自动巡检、状态变化才告警。**日常查健康先看它。**
- **部署前必读顺序**：SYSTEM.md → TOPOLOGY.md → 各模块 README。任何陌生 AI 按此顺序读完即可完整部署，不会漏掉沙漏。
- 维护规则：改端口/布局/仓库 → 同步改 TOPOLOGY.md；改数据流/部署顺序/新增坑 → 同步改本文件；改巡检项/阈值 → 同步改 SYSTEM_HEALTH.md + scripts/system_health_check.sh。

---
*事实来源：沙漏链路诊断-20260810.md（四层架构/4761 条/双写/sender/feed 计数）、NexSandglass README+ARCHITECTURE、LMS README+docs/ARCHITECTURE.md、memory-integration-layer README+interfaces/README、Agent OS TOPOLOGY/env.local/start_all.sh/status_all.sh/DEPLOY-GLOBAL/DOUBT-SYSTEM/iso-sand handlers.py+event_schema.yaml、轻如烟 SELF_PULSE_README+pulse-cron.sh+wake_client.py+salience_gate.py+sleep_pressure.py、glue-memory-injector index.js+memory-recall.js+openclaw.plugin.json、edit-web.py:209,302、sandglass_http_api.py。待核实项：双写源的具体前端路径（诊断 P0-1 未定位）、decision_particles 原调用方（P1-2）。*

## 6. 设计遗产（明确不修，2026-08-10 标注）

| 模块 | 状态 | 理由 |
|------|------|------|
| **L3 画像（persona 蒸馏）** | 🗄️ 遗产 | 职责与 LMS 目的层重叠；LMS 是 FEP 框架（有理论依据），画像维护 6/16 后停摆，无调用方。需要"人类可读自我描述"时再议 |
| **L4 决策粒子（决策追踪/偏移率/幽灵决策）** | 🗄️ 遗产 | 全库仅 1 条、feed_all 零调用方、从未接入链路、历史上无深入讨论。决策追踪职责由 **LMS 目的层 precision 调整**承担，是旧方案的影子，修的成本>收益 |

> 判定依据：《沙漏链路诊断-20260810.md》+ 沙漏搜索实证（2026-08-10 23:08 dandan 确认：画像/L4 没必要修）
