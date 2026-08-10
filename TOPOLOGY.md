# TOPOLOGY.md — 系统权威拓扑（单一事实源）

> ⚠️ **部署前必读 SYSTEM.md（数据流视角总图）** —— 本文件是模块清单视角；
> 明暗双线/部署顺序/运行时数据流/踩坑/3分钟巡检法在 `SYSTEM.md`（同仓库根目录）。
> 部署顺序：先 SYSTEM.md → 再本文件 → 后各模块 README，保证不漏掉沙漏。

> 2026-08-10 建立（dandan 指示：模块分散部署导致"这找不到那找不到"，需要权威拓扑 + 模块契约声明）
> **本文件是唯一权威入口**：任何模块的 README 都指向这里；新增/迁移模块必须同步更新本文件。
> 版本约定：本文件随 `tdx1146/agent-os` 仓库维护，远端地址以 GitHub 为准（**非本地路径**）。

---

## 0. 一句话总览

```
                     ┌─────────────────────────────────────────────┐
                     │  OpenClaw Gateway（毛毛，主 AI，:10554）      │
                     │  插件: deepseek + glue-memory-injector       │
                     └──────┬───────────────────────┬───────────────┘
                            │ hooks/wake（唤醒）     │ /recall 记忆注入
              ┌─────────────▼───────────┐   ┌───────▼────────────────┐
              │  Agent OS 总线（iso-sand）│◄──┤  胶水层 glue (:19000)   │
              │  scheduler/consumer     │   │  doubt_adapter 怀疑账本  │
              │  event_bus.jsonl        │   └───────┬────────────────┘
              └──┬──────────┬──────────┘           │ storeTurn / feed
                 │          │                      ▼
   ┌─────────────▼───┐  ┌───▼────────────┐   ┌──────────────┐
   │ doubt-system    │  │ 玄鉴 verify    │   │ LMS 活体记忆  │
   │ (夜巡/反教条)    │  │ daemon（5min） │   │ (:8190/:8191) │
   └─────────────┬───┘  └───────────────┘   └──────┬───────┘
                 │  doubt.episode 事件              │ /feed 塑形
                 └──────────────┬──────────────────┘
                                ▼
                     ┌──────────────────────┐
                     │ 沙漏 sandglass (:17333)│  ← 落沙日志/状态中枢
                     │ + 轻如烟编辑器 (:18888)│
                     └──────────────────────┘
```

---

## 1. 模块清单（按职责）

| # | 模块 | 远端仓库（GitHub，权威） | 本地部署路径 | 端口 / 健康端点 | 职责 |
|---|------|--------------------------|--------------|-----------------|------|
| 1 | **LMS 活体记忆** | `github.com/tdx1146/living-memory-system`（**main**，公开 2026-08-10） | `/vol2/1000/AI专用/living-memory-system-cloud` | `:8190` /health；`:8191` 控制口 | 活体记忆：turn/熵/惊讶/目的、自动做梦、self_ref、快照 |
| 2 | **胶水层 glue** | `github.com/tdx1146/memory-integration-layer`（**main**，公开） | `/vol2/1000/AI专用/memory-integration-layer` | `:19000` /health | 记忆注入（读侧 /recall）、落沙（写侧 storeTurn）、doubt_adapter 怀疑账本、lms_client SDK |
| 3 | **Agent OS 总线** | `github.com/tdx1146/agent-os`（main） | `/vol2/1000/AI专用/Agent OS` | 无端口（文件总线 + 调度器） | 事件总线 event_bus.jsonl、scheduler/consumer、stack_ctl 一键运维、**本拓扑的宿主** |
| 4 | **doubt-system 怀疑系统** | `github.com/tdx1146/agent-os` → `doubt-system/` 子目录 | `/vol2/1000/AI专用/Agent OS/doubt-system` | 无端口（cron 23:30 夜巡） | 持续自我怀疑：memory_trust 信任度、夜巡旁观者、反教条复核、doubt_hook 部署钩子 |
| 5 | **玄鉴 verify_daemon** | 以姐姐侧 GitHub 仓库为准（dandan 2026-08-10 确认已在 GitHub；本机目录无 git remote，不自动上传） | `/vol2/1000/AI专用/AgentOS-IsoSand/同构沙盘` | 无端口（守护进程，5min 巡检） | 对外部知识/文件变更的校验审计（keyword_v0.1） |
| 6 | **沙漏 sandglass** | 以姐姐侧 GitHub 仓库为准（dandan 2026-08-10 确认已在 GitHub；本机目录无 git remote，不自动上传） | `/vol2/1000/AI专用/所有自动化/轻如烟` | `:17333`（HTTP API）；`:18888` 编辑器 | 落沙日志 + 状态中枢（metrics.jsonl、persona、sleep_pressure、doubt.db） |
| 7 | **self_pulse 自主唤醒** | ⚠️ 属沙漏（无独立远端） | `/vol2/1000/AI专用/所有自动化/轻如烟/scripts/` | cron `*/10` | 唤醒链：salience_gate → sleep_pressure（体力）→ wake_client → hooks/wake |
| 8 | **OpenClaw Gateway** | 官方（openclaw） | `/vol1/@apphome/trim.openclaw/data` | `:10554` | 主 AI 运行时（毛毛本体） |

---

## 2. 模块间契约（谁调用谁）

| 调用方 | → | 被调用方 | 契约/接口 |
|--------|---|----------|-----------|
| self_pulse | → | LMS | `GET /status/{sid}`（熵/目的/惊讶度） |
| self_pulse | → | OpenClaw | `POST /hooks/wake`（A 通道，实证 8/7） |
| 胶水层（读侧） | → | 沙漏/LMS/向量 | `GET /recall`（每轮注入记忆进提示词） |
| 胶水层（写侧） | → | 沙漏 | `storeTurn` 落沙 |
| doubt_adapter | → | Agent OS 总线 | `doubt.episode` 事件（v1.1 契约，需 `DOUBT_BUS_FILE` 环境变量） |
| Agent OS consumer | → | LMS | `lms.feed` 订阅（doubt.episode → `POST /feed` 塑形） |
| 夜巡 night_patrol | → | 沙漏 | 写 findings（tag=旁观者-警讯） |
| 夜巡 night_patrol | → | 总线/operation_log | 读当天 FAIL/变更行 + crontab 快照 |
| verify_daemon | → | operation_log | 追加 WARN（连续 3 FAIL 时）+ doubt_hook 怀疑 |
| doubt_hook | → | doubt_adapter | 部署/异常 → novelty/conflict 怀疑 → 账本 + 总线 |

---

## 3. 关键文件地图（跨模块，最常被问"在哪"）

| 要找的东西 | 位置 |
|------------|------|
| 事件总线 | `Agent OS/iso-sand/data/event_bus.jsonl` |
| 操作日志 | `Agent OS/iso-sand/data/operation_log.jsonl` |
| 怀疑账本 | `沙漏/sandglass/doubt.db`（表 doubt_episode / memory_trust） |
| 睡眠压力状态 | `沙漏/sandglass/sleep_pressure.json` |
| 待办源 | `workspace/memory/backlog.md`（self_pulse 每 10min 扫描） |
| 记忆文件 | `workspace/memory/*.md`（daily note、诊断、实施报告） |
| 长期记忆 | `workspace/MEMORY.md` |
| 配置中心 | `Agent OS/env.local`（各模块共享，零硬编码） |
| 总线事件 schema | `Agent OS/iso-sand/deploy/event_schema.yaml` |
| 怀疑系统文档 | `Agent OS/DOUBT-SYSTEM.md` |
| 本拓扑 | `Agent OS/TOPOLOGY.md`（本文件） |

---

## 4. 部署正确性自检（新机器/姐姐部署后必跑）

```bash
# 1. 全栈状态（6 服务进程/端口/健康）
cd /vol2/1000/AI专用/Agent\ OS && bash status_all.sh

# 2. 配置中心一致性
bash stack_ctl.sh doctor

# 3. 怀疑系统三把锁（crontab 是否被意外覆盖）
crontab -l | grep -E "pulse-cron|night_patrol|watchdog"   # 三条都要有

# 4. 怀疑总线开关（doubt.episode 是否发布）
grep DOUBT_BUS_FILE /vol2/1000/AI专用/memory-integration-layer/.env
```

---

## 5. 仓库全景与废弃说明（2026-08-10 更新，防混乱根源）

> **规则：本清单是 tdx1146 名下全部仓库的唯一权威地图。废弃 = GitHub Archived（只读）或本表标注。**
> 之前混乱根源：分支/仓库一次次失忆时乱建，没人标注废弃。现在：**三仓统一 main，全部公开，废弃仓已 archive。**

| 仓库 | 状态 | 默认分支 | 说明 |
|------|------|---------|------|
| `living-memory-system` | ✅ 活跃 | main | LMS 活体记忆（2026-08-10 起公开） |
| `memory-integration-layer` | ✅ 活跃 | main | 胶水层 glue（公开） |
| `agent-os` | ✅ 活跃 | main | **本拓扑宿主**（公开） |
| `edit-web.py` | ✅ 活跃 | main | 轻如烟编辑器 v1~v5.1（公开） |
| `qingruyan-scripts` | ✅ 活跃 | main | self_pulse 唤醒链脚本（公开） |
| `glue-memory-injector` | ✅ 活跃 | main | OpenClaw 记忆注入插件（公开） |
| `monument-network` | ⚠️ 待确认 | main | 丰碑网络（早期组件，内容已被 agent-os 吸收？未 archive） |
| `agent-os-sandglass` | 🗄️ 已废弃 Archived | main | 早期拆分组件，已被 agent-os 吸收（2026-08-10 archive） |
| `agent-os-iso-sand` | 🗄️ 已废弃 Archived | main | 同上 |
| `agent-os-kernel` | 🗄️ 已废弃 Archived | main | 同上 |

---

## 6. 已知缺口（2026-08-10 审计）

1. 轻如烟/玄鉴的远端仓库：**以姐姐侧 GitHub 版本为准**（dandan 2026-08-10：本机不自动上传）。本机目录无 git remote 属正常。
2. ~~living-memory-system 为私有仓库~~ → **2026-08-10 已公开，默认分支 main**。
3. 本文件建立后，各模块 README 需补「系统定位」段指向本文件（已完成：见各 README 顶部）。
4. **待重启生效**：:8190 已重启（2026-08-10 10:31），阶段 2 的 T2.3 归档检索/T2.6 审计/T2.8 算法治理已加载；T2.2 健康检查调度、:8191 控制口、codex/workbody 接入尚未落地（C 类）。

---

> 维护规则：**改模块布局/端口/仓库/分支时，必须同步改本文件**。本文件是唯一权威，各 README 只是指针。
