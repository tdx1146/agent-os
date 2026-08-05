# DOUBT-SYSTEM — 持续自我怀疑系统（本机接入说明）

> 部署：2026-08-05（Phase 6 补链，dandan 指示"聪明 = 持续自我怀疑，这是 AgentOS 的既定设计"）
> 代码源：GitHub `tdx1146/agent-os` 仓库 `doubt-system/` 目录（7 个文件）
> 本机位置：`/vol2/1000/AI专用/Agent OS/doubt-system/`

---

## 一、这是什么（给后来者的一句话）

**持续自我怀疑 = 聪明。** 本系统把"怀疑"工程化：每条记忆带信任度（被反驳就降权）、每次怀疑闭环写账本、每天 23:30 夜巡复盘当天、反教条复核挑最硬记忆质疑"还成立吗"。它与 LMS（记得承诺）配合：**记得 + 怀疑 = 不教条**。

## 二、组件与分工

| 文件 | 职责 |
|------|------|
| `memory_trust.py` | 记忆信任度：`trust_weight = 1/(1+age_days) × (1-rebuttal/(reference+1))`，被反驳≥2次强制 0.1；数据存 `doubt.db` 的 `memory_trust` 表（不 ALTER 沙漏主表） |
| `night_patrol.py` | 夜巡数据汇总（当天沙漏对话/记忆文件/operation_log FAIL/怀疑账本 → `/tmp/night_patrol_input.json`，纯数据不调 LLM） |
| `night_patrol_run.sh` | 夜巡执行器（cron 23:30）：汇总 → `openclaw agent` 隔离子代理旁观 → findings 校验写沙漏 → 反教条复核；flock 单实例锁 + 每日幂等 marker |
| `night_patrol_findings.py` | 旁观者产出校验/指纹去重/写沙漏（tag=旁观者-警讯）/高价值项追加 observer-alerts.json |
| `night_patrol_dogma.py` | **反教条复核**：top10 高频记忆注入"可能已过时"复核，每天≤3条 |
| `cross_review.py` | 跨实例互审（默认注释，CROSS_REVIEW=1 启用） |
| `test_memory_trust.py` | 自测 |

## 三、胶水层怀疑账本（doubt_adapter）

- 位置：`memory-integration-layer/interfaces/adapters/doubt_adapter.py`
- 职责：`doubt_episode` 行为账本（SQLite，`sandglass/doubt.db`），触发类型：`conflict / stakes / fok / surprise / novelty / user_correction`；月度统计注入 persona（习惯奖励回路）
- **总线发布（Phase 6 新增）**：`store_doubt()` 成功后，若环境变量 `DOUBT_BUS_FILE` 指向权威总线，追加 `doubt.episode` 事件（v1.1 契约）→ 消费者 `lms.feed` 订阅 → **POST LMS /feed 喂塑形**（自我怀疑喂潜意识）。默认不发布，fail-open。

## 四、本机通电状态（2026-08-05）

| 项 | 状态 |
|----|------|
| doubt.db | ✅ 已建（`/vol2/1000/AI专用/所有自动化/轻如烟/sandglass/doubt.db`），第一条记录=2026-08-05 user_correction（Docker 承诺疏漏） |
| 路径修正 | ✅ 全部 7 文件 `/vol1/@team/qh团队/...` 旧路径 → `/vol2/1000/AI专用/...`（Phase 6 修 health-check 同类） |
| 总线接入 | ✅ `doubt.episode` 已注册 schema v1.1 + lms.feed 已订阅（handlers.py） |
| 端到端 | ✅ 写怀疑 → 总线 → lms.feed → LMS /feed 200 OK |
| 夜巡 cron | ✅ `30 23 * * *` 已入 crontab（每日 23:30） |
| 胶水层测试 | ✅ tests/test_doubt_adapter.py 19 passed |

## 五、接入方式（后来者照做）

```bash
# 1. 拉代码（已在本机 Agent OS/doubt-system/）
# 2. 修正旧路径（如从姐姐机器同步过来）：
#    sed -i 's|/vol1/@team/qh团队/QH/AI专用|/vol2/1000/AI专用|g' *.py *.sh
# 3. 环境变量（胶水层 .env）：
#    DOUBT_BUS_FILE=/vol2/1000/AI专用/Agent OS/iso-sand/data/event_bus.jsonl
# 4. 写一条怀疑记录测试：
#    python3 -c "from interfaces.adapters.doubt_adapter import store_doubt; store_doubt({'trigger_type':'novelty','suspicion':'测试','topic':'t','user_reaction':'acknowledged'})"
# 5. 夜巡 cron：30 23 * * * bash .../doubt-system/night_patrol_run.sh
```

## 六、关键备注（重要！）

1. **夜巡第 2 步依赖 `openclaw agent` 命令**（隔离子代理当"时间旁观者"）——本机 OpenClaw 5.4 支持；若换环境需确认该命令可用，否则旁观者环节降级（数据汇总+反教条复核仍工作）
2. **每日幂等**：marker 文件 `/vol1/@apphome/trim.openclaw/data/workspace/logs/night_patrol.last_run`——cron 与调度器双源同天只分析一次
3. **doubt.db 是沙漏数据目录下的独立库**——别删，删了怀疑史清零
4. **自我怀疑喂 LMS 的意义**（dandan 定位）：LMS 记得承诺（塑形）+ doubt-system 怀疑承诺（反教条）= 不教条。教条 = 只登记不质疑；聪明 = 登记 + 持续质疑
5. **与玄鉴的关系**：玄鉴=对外部知识的判断/评分（延后中）；doubt-system=对自身记忆与承诺的怀疑（本机已通）。两者是"审外"与"审己"
