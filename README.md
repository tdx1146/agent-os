# Agent OS — 毛毛（轻如烟）自主系统中枢

> **本仓库是整套「AI 活体记忆系统」的地图与部署中心宿主**：事件总线、调度、怀疑系统、运维入口都在这里。
> 2026-08-12 更新（成果系统化保存）：站在「任何陌生 AI / 开发者第一次接手」的角度重写——拿到本仓库，照本文档能接住整套系统，不两眼一抹黑、不部署这个少那个。

---

## 一、系统是什么（3 句话）

1. **它是一套「AI 活体记忆系统」**：主 AI（毛毛，跑在 OpenClaw 里）每轮对话完整落沙、每轮被记忆注入、空闲时做梦巩固——不再"关掉窗口就失忆"。
2. **它由明暗双线构成**：**沙漏（明线）**把每句话一字不丢地存成明文流水账（保底，丢了它一切免谈）；**LMS 活体记忆（暗线）**用自由能原理（FEP）从对话流动中提炼结构（熵/惊讶度/目的），让记忆像海马体一样自己巩固、遗忘、演化。明线保"不忘"，暗线保"懂"。
3. **它由方法论驱动**：设计→审计→实施→再审计的闭环 + 契约层（CONTRACTS.yaml 机器校验）+ 健康巡检基线（system_health_check.sh）——"修完这个又坏那个"被当作系统性缺陷对待，而不是单点打补丁。

一句话数据流：**对话 → 编辑器落沙（明线）→ 插件经 glue 检索注入（送回对话）→ LMS feed/每轮 store 塑形（暗线）→ 做梦巩固 → 回魂注入。**

---

## 二、怎么上手（3 步）

```bash
# ① 读文档（按顺序，缺一不可）
#    SYSTEM.md（数据流/部署中心）→ TOPOLOGY.md（模块清单）→ 本文档 → 各模块 README
#    ★ 新成果速查：成果存档索引-20260812.md（8/11-8/12 全部成果的标题/路径/状态）

# ② 一键部署（配置中心 env.local 是唯一写绝对路径的地方；clone 见下方「仓库一览」）
cd "Agent OS"
bash deploy.sh          # 一键：bootstrap 自动 clone 6 仓/venv/.env/数据目录 → 前置检测(缺→自动修) → 拉起 → 验证 → cron 检查
bash deploy.sh status   # 验证活着（10 分钟清单见 SYSTEM.md §3.5）
```

## 二·仓库一览（6 仓 + 1 插件仓，全部公开无需 token）

> 2026-08-13 更新（演练 G11）：README 原“三仓”口径过时。实际需要 6 个仓库 + 1 个插件仓，
> clone 命令集中在此，可直接复制（保持相对布局即可，绝对路径只写进 env.local）。
> **一键替代**：clone 完 agent-os 后 `cd agent-os && bash deploy.sh` —— bootstrap 会自动 clone 其余全部。

```bash
# 0) 主仓（本仓库）
git clone https://github.com/tdx1146/agent-os.git
cd agent-os

# 1) 活体记忆 LMS（→ LMS_HOME）
git clone https://github.com/tdx1146/living-memory-system.git ../living-memory-system-cloud
# 2) 胶水层（→ GLUE_HOME）
git clone https://github.com/tdx1146/memory-integration-layer.git ../memory-integration-layer
# 3) 沙漏源码（→ SANDGLASS_SOURCE，nyx fork；LIGHT_HOME=沙漏数据+源码+编辑器所在）
mkdir -p ../所有自动化/轻如烟
git clone https://github.com/tdx1146/nyx.git ../所有自动化/轻如烟/sandglass_source
# 4) 轻如烟编辑器（→ EDITOR_HOME = LIGHT_HOME/scripts；⚠️ 缺口 #3 合并前为旧版，self_pulse 用 agent-os/self_pulse 覆盖）
git clone https://github.com/tdx1146/edit-web.py.git ../所有自动化/轻如烟/scripts
# 5) 玄鉴：已内置在 agent-os/xuanjian/（无需单独 clone；data/ 首次运行自动创建）
# 6) OpenClaw 插件 glue-memory-injector（→ PLUGIN_HOME，默认 ~/.openclaw/plugins）
mkdir -p ~/.openclaw/plugins
git clone https://github.com/tdx1146/glue-memory-injector.git ~/.openclaw/plugins/glue-memory-injector
```

> 注：`living-memory-system` 与本地目录名 `living-memory-system-cloud` 的差异是历史命名（cloud = 云端嵌入部署）；
> bootstrap 的仓库注册表在 `deploy.sh` 的 `REPOS`（可用 `GITHUB_BASE` 环境变量覆盖，供镜像/内网）。
> 上述 clone 全部可省略——`bash deploy.sh` 的 bootstrap 阶段会自动完成（幂等）。

---

## 三、完整组件清单（一个都不能少）

> 角色：明线=保底流水账｜暗线=FEP 塑形｜胶水=统一编排｜总线=事件骨架｜监督=怀疑/校验｜唤醒=自主醒来｜宿主=运行容器

| # | 组件 | 角色 | 在哪（本地/仓库） | 端口/接口 | 最容易漏？ |
|---|------|------|------------------|-----------|-----------|
| 1 | **沙漏 NexSandglass** | 明线·保底 | `所有自动化/轻如烟/`（sandglass_source 源码，数据 sandglass/） | `:17333` HTTP API；权威源 `sandglass.txt` | ⚠️ **最容易漏**（只看 LMS 文档就以为系统完整；它是失忆后找回自己的最后底牌） |
| 2 | **LMS 活体记忆** | 暗线·塑形+质检 | `living-memory-system-cloud/`（必须 .venv+.env） | `:8190` 主口（/health /status /feed /react）、`:8191` 控制口、MCP lms-memory/lms-http | 容易漏 .env 不 source → 静默降级 |
| 3 | **胶水层 glue** | 胶水·统一编排 | `memory-integration-layer/` | `:19000`（/recall /soul /store /react） | 中（依赖沙漏+LMS+向量都活） |
| 4 | **Agent OS 总线 iso-sand** | 总线·事件骨架 | `Agent OS/iso-sand/`（本仓库内） | 无端口，文件总线 `data/event_bus.jsonl` | 中（scheduler/consumer 两个进程都要起） |
| 5 | **玄鉴 verify_daemon** | 监督·审外 | `Agent OS/xuanjian/`（2026-08-12 并入本仓，源码随仓分发；data/ 不随仓） | 无端口，5min 巡检 operation_log | 高（无端口守护进程，不起也不报错） |
| 6 | **doubt-system 怀疑系统** | 监督·审己 | `Agent OS/doubt-system/`（本仓库内） | 无端口，cron 23:30 夜巡 | 高（纯 cron，不部署就是"没怀疑"） |
| 7 | **self_pulse 自主唤醒** | 唤醒 | `所有自动化/轻如烟/scripts/`（pulse-cron.sh + self_pulse_cli.py + salience_gate + sleep_pressure + wake_client） | cron `*/10`；唤醒出口 `WAKE_CHANNEL`（a=hooks/wake，b=chat.send 注入[梦醒]） | 高（一套脚本不在一个仓，散在轻如烟 scripts/） |
| 8 | **OpenClaw 插件 glue-memory-injector** | 胶水·注入 | OpenClaw plugins 目录（`glue-memory-injector/`） | `before_prompt_build` hook；`[回魂]+[记忆注入]` 前缀 | 高（在 OpenClaw 目录，不在任何仓库根；改后需 gateway 重载才生效） |
| 9 | **轻如烟编辑器 edit-web** | 明线·写入口 | `所有自动化/轻如烟/scripts/edit-web.py`（`/vol1/轻如烟/轻如烟` 与 `/vol2/1000/AI专用/所有自动化/轻如烟` 是同一文件，bind mount） | `:18888`；真正的落沙写入者 | 高（没它对话不进 sandglass.txt，明线断） |
| 10 | **OpenClaw Gateway** | 宿主 | `/vol1/@apphome/trim.openclaw/data` | `:10554`（hooks/wake） | 低（官方安装） |
| 11 | **丰碑网络 monument-network** | 监督·远期遗产 | `丰碑网络/`（独立目录） | 无端口 | ⚠️ **半成品**：磨损/加固生态**从未接线**（孤儿模块）；只有个体丰碑+玄鉴评分跑通过。**当前不是运行依赖**，是"将来复活"的资产（对齐调研见 丰碑LMS对齐调研-20260812.md） |

**最容易漏的三个**：① 沙漏（明线底座，最容易以为"有 LMS 就够了"）② 玄鉴（无端口守护进程，不起也不报错）③ 插件（在 OpenClaw 目录里，且改后不重载 gateway 就不生效）。

---

## 四、部署顺序（依赖关系，反了就是"起了但全在降级"）

> **依赖链：沙漏（零依赖，数据底座）→ LMS（依赖向量+.env）→ 胶水（依赖沙漏+LMS+向量）→ 总线（消费者依赖胶水/LMS）→ 玄鉴（依赖 operation_log）**

| 步 | 组件 | 为什么先 | 验证命令 |
|----|------|---------|---------|
| ① | 沙漏 :17333 | 零依赖；txt 是全局权威源 | `curl http://127.0.0.1:17333/api/health` |
| ② | LMS :8190 | 依赖向量服务 + `.env`（必须 `set -a; . ./.env; set +a`） | `curl http://127.0.0.1:8190/status/main`（turn_count 非空，空=降级） |
| ③ | 胶水 :19000 | 依赖沙漏+LMS+向量都活 | `curl http://127.0.0.1:19000/health`（backends 非 degraded） |
| ④ | 总线 scheduler+consumer | consumer 的 LmsFeedHandler 依赖 LMS /feed | `tail -3 iso-sand/data/event_bus.jsonl`（时间戳是当前） |
| ⑤ | 玄鉴 | 依赖 operation_log（总线消费者产出） | `cat xuanjian/data/daemon.pid`（data/ 首次运行自动创建） |
| ⑥ | crontab（唤醒链/夜巡/备份/自启） | 常驻守护 + 开机自启 | `crontab -l`（全表见 SYSTEM.md §3.4） |
| ⑦ | 编辑器 :18888 | 落沙写入者 | 发消息 → `tail -3 sandglass.txt` 出现新行 |
| ⑧ | OpenClaw 插件+MCP | 记忆送回对话的唯一入口 | 发消息 → `/tmp/glue-hook-debug.log` 有 INJECTED |

**实际上 ①~⑤ 由 `bash start_all.sh` 一键完成**（内部已做 health 检查）。详细手册见 `SYSTEM.md §3`。

---

## 五、外部依赖（部署者必须自己准备）

| 外部依赖 | 为什么必须 | 怎么准备 |
|---------|-----------|---------|
| **embed 向量服务（bge-m3，OpenAI 兼容 /v1/embeddings）** ⚠️最关键 | LMS 感官层嵌入 + 胶水向量都用它；**没有它 = LMS/胶水全部静默降级，感官层就瞎了**（HF 在本机不可达，`LMS_EMBEDDER` 不能回 pretrained） | 手机/任意机器跑 Ollama + bge-m3（1024 维），暴露 `http://<host>:11435/v1/embeddings`，写入 `LMS_CLOUD_EMBED_URL`（LMS `.env` + env.local）与 `VECTOR_URL`（env.local） |
| **DeepSeek API Key** | LMS LLM 能力（自述蒸馏等） | 写入 `$LMS_HOME/.env` 的 `DEEPSEEK_API_KEY`；不填 = LLM 功能禁用但记忆核心仍工作 |
| **OpenClaw Gateway** | 主 AI 宿主（插件/MCP/hooks） | 需支持 `before_prompt_build` hook + MCP 注册 + `/hooks/wake` 端点；版本以 OpenClaw 官方为准 |
| **node（≥18）** | OpenClaw 运行时 + 插件 | 部署机器需安装 |
| **GitHub 6 仓 + 1 插件仓** | clone 代码 | `agent-os` / `living-memory-system` / `memory-integration-layer` / `nyx` / `edit-web.py` / `glue-memory-injector` 均 **main 分支公开**（2026-08-10 起），**clone 不需要 token**；只有 push 才需凭据（本机已配 credential helper，**token 不进 git、不进文档**）。玄鉴内置在 agent-os/xuanjian/。集中 clone 命令见上方「仓库一览」，或 `bash deploy.sh` 自动完成 |
| **手机记忆网关（可选）** | OpenClaw MCP shouji-memory 桥接 | `SHOUJI_MCP_URL`；缺省不影响本地链路 |

---

## 六、文档地图（先读哪个、在哪找）

| 文档 | 路径 | 内容 | 什么时候读 |
|------|------|------|-----------|
| **部署中心** | `SYSTEM.md`（本仓库） | 数据流总图 + 部署顺序 + 运行时旅程 + 踩坑 + 10 分钟验证清单 | **部署前必读第一份** |
| **模块清单** | `TOPOLOGY.md`（本仓库） | 组件位置/端口/仓库/契约表/文件地图，单一事实源 | 部署前第二份；改端口/布局必须同步改它 |
| **成果存档索引** | `成果存档索引-20260812.md`（本仓库，新增） | 8/11-8/12 全部成果：标题/文档路径/状态/一句话说明 | 想了解"系统最近有什么新东西"时 |
| **契约层** | `CONTRACTS.yaml` + `scripts/contract_check.sh`（本仓库） | 组件间接口机器可校验（38+ 校验项，退出码 0/1/2） | 改任何跨组件接口前；日常 `*/30` cron 自动跑 |
| **健康巡检** | `SYSTEM_HEALTH.md` + `scripts/system_health_check.sh`（本仓库） | 20 项巡检自动化，审计标准前置基线 | 任何审计类任务开始前（方法论 v1.1 强制） |
| **故障恢复** | `RECOVERY.md` + `dashboard.html`（本仓库） | 不懂代码也能照做的恢复预案 + 可视化看板 | 出问题时 |
| **怀疑系统** | `DOUBT-SYSTEM.md`（本仓库） | 夜巡/反教条/doubt_hook 说明 | 接触怀疑系统时 |
| **部署细节** | `DEPLOY-GLOBAL.md` / `DEPLOYMENT.md`（本仓库） | 配置中心/一键部署 / Phase 6 细节 | 部署卡壳时 |
| **调度方法论** | `/vol2/1000/AI专用/子AI调度方法论-v1.0.md`（内容为 v1.1） | 变更审批红线 + 派遣子 AI 流程 + 审计前置基线 + 契约层用法 | **每次派遣子 AI 前必读** |
| **调研/设计文档库** | `/vol2/1000/AI专用/`（各 `*-2026081x.md`） | 惊讶度/体验层/梦醒回路/双向塑形/提取层/召回/丰碑对齐等全部设计与调研 | 要深入某一主题时，先看 `成果存档索引-20260812.md` 挑文档 |
| **本文件** | `README.md` | 上手总入口 | 第一次接手 |

**完整文档清单与每份文档的一句话说明 → 看 `成果存档索引-20260812.md`。**

---

## 七、常见坑（今晚血泪，按杀伤力排序）

1. **SIGUSR1 不重载插件**：改完插件只发一次 SIGUSR1 无效——插件代码要 **gateway 完全重启**才加载；且 SIGUSR1 **禁止连击**（第二次在活跃会话中 = forced restart = 杀 session）。SIGUSR1 前确认 session 空闲（无 pending 模型调用）。
2. **key 绝不进 git**：`.env`/`*.local` 已在 .gitignore；token 只存 credential helper（chmod 600）或环境变量。**不要**把 key 写进文档/记忆/日志/commit。
3. **LMS `.env` 必须 source**：启动前 `set -a; . ./.env; set +a`。不 source = **静默降级**（embed 变 simple、LLM 不启用、`/health` 却显示正常）——"部署了但没生效"的头号元凶。
4. **4:00 会话重置已永久关闭**：openclaw.json 已设 `session.reset: {mode: idle, idleMinutes: 999999}`（备份 .bak-20260811-0119-session-reset）。**不要**把它改回去——那是失忆感的历史元凶之一；现在由 `session-reset-watchdog`（cron `*/2`）守护归档。
5. **沙漏被遗忘**：部署顺序第一步永远是沙漏。没有它：没有流水账、没有回魂"最近"、AI 失忆后无法找回自己。
6. **`LMS_EMBEDDER` 不是 cloud / 向量服务不可达**：HF 在本机不可达，必须 `LMS_EMBEDDER=cloud` + `LMS_CLOUD_EMBED_URL`。嵌入挂了 → LMS 与胶水向量全部降级。
7. **总线心跳 ≠ 沙漏数据**：`event_bus.jsonl` 里大量 `sandglass.heartbeat` 是**调度器存活心跳**，不代表沙漏活着。判断沙漏只能看 `sandglass.txt` mtime/行数。
8. **双写/sender 错标/500 截断（已修，别"修回去"）**：`SANDGLASS_DEDUP_WINDOW`、`SANDGLASS_SENDER_MAP`、`SANDGLASS_MAX_TEXT_LEN` 三个环境变量是 2026-08-11 P0-1/2/3 补丁的开关，新环境别调回旧值。
9. **读侧超时静默失败**：插件 HTTP 超时 15000ms、glue 用 ThreadingHTTPServer。改小超时/改回单线程 → 记忆注入全部静默 MISS，AI 表现为"失忆"但不报错。
10. **生产 8190 跑旧代码**：改完 LMS 必须重启 8190（`set -a; . ./.env; set +a` + 重启）；插件改完必须重载 gateway。否则 `/react` 404 / 无 doubt 字段 / 回魂无解读段，**且不报错**（glue fail-open 优雅降级成旧行为）。
11. **子代理样板污染 [记忆注入]**：`_GARBAGE_TEXT_RE` 纯增量正则（入口过滤防新增）。新调度样板串出现时**往正则里加，勿删现有条目**。
12. **查询污染召回（已修，召回 L1）**：插件曾把含 untrusted metadata 的完整提示词当检索 query → 记忆注入全是编辑器模板。已修：插件复刻 `stripInboundMetadata` 净化 + 子代理轮跳过 + glue 入口兜底净化。

**完整 17+ 条坑清单 → `SYSTEM.md §5`。**

---

## 八、快速入口（原有内容保留）

- **部署中心（先读这个）**：👉 [`SYSTEM.md`](./SYSTEM.md) — 数据流总图 + 部署顺序 + 踩坑 + 10 分钟验证清单，陌生 AI 照着能完整部署
- **系统全图（模块视角）**：👉 [`TOPOLOGY.md`](./TOPOLOGY.md) — 8 个模块的位置/端口/仓库/契约，单一事实源
- **成果存档索引（8/11-8/12 全部成果）**：👉 [`成果存档索引-20260812.md`](./成果存档索引-20260812.md)
- 一键运维：`bash stack_ctl.sh status|doctor|start`（配置中心 `env.local`）
- 服务状态：`bash status_all.sh`（6 服务进程/端口/健康）
- 事件总线：`iso-sand/data/event_bus.jsonl`（v1.1 契约，schema 见 `iso-sand/deploy/event_schema.yaml`）
- 怀疑系统：`doubt-system/`（详见 `DOUBT-SYSTEM.md`）
- 部署指南：`DEPLOY-GLOBAL.md`（配置中心/一键部署）/ `DEPLOYMENT.md`（Phase 6 细节）

## 子模块

| 目录 | 职责 |
|------|------|
| `iso-sand/` | 事件总线（scheduler/consumer）、operation_log |
| `doubt-system/` | 持续自我怀疑（夜巡/反教条/doubt_hook） |
| `docker/` | 容器化编排（5 服务） |
| `kernel/` | 内核层规范（预留） |
| `docs/` | 设计文档（自主唤醒调研/诊断等） |
| `scripts/` | contract_check.sh / system_health_check.sh / gen_dashboard.sh / sandglass_sync.sh |
| `TOPOLOGY.md` | **权威拓扑（本仓库的核心文档）** |
| `SYSTEM.md` | **部署中心（数据流视角的唯一事实源）** |
| `CONTRACTS.yaml` | **契约注册表（机器可校验）** |
