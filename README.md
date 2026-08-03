# Agent OS

Agent OS 是"姐姐"（tdx1146 实例）的智能体操作系统：围绕 OpenClaw 网关，把沙漏记忆、内核快照、纪念碑、插件注入、怀疑系统与隔离子代理粘合成一个可自省、防回声室、可跨实例互审的整体。

> 本仓库只纳管**代码与文档**；运行数据（沙漏库、内核快照、纪念碑数据、iso-sand 数据）在运行目录中存在但被 `.gitignore` 排除，不入版本管理。

---

## 系统架构总览

| 目录 | 职责 | 是否入库 |
|------|------|----------|
| `kernel/` | 内核快照与自省：PURPOSE/VERSION、操作日志、偏离记录、快照、githooks | ❌ 运行目录（gitignore） |
| `sandglass/` | 沙漏记忆系统（NexSandglass v2.9.9）：对话记忆库、decision_particles | ❌ 运行目录（gitignore） |
| `monument/` | 纪念碑：长期索引、candidates、roadmap、代码与种子语料 | ❌ 运行目录（gitignore） |
| `iso-sand/` | 隔离子沙盒：design/deploy/docs、operation_log.jsonl、备份、githooks | ❌ 运行目录（gitignore） |
| `plugins/` | OpenClaw 插件（当前生效代码）：`qingruyan-behavior-enforcer`（沙漏注入 v6.4）、`sandglass-injector` | ✅ |
| `doubt-system/` | 怀疑系统脚本：记忆信任度 / 夜巡 / 反教条 / 跨实例互审（见下） | ✅ |
| `knowledge-graph/` | 知识图谱：SKILL、VERSION、图谱 JSON、生成脚本 | ✅ |
| `startup/` | 部署与启动：部署脚本、配置审计、使用指南、端口与服务 | ✅ |
| `docs/` | 文档：元认知协议、理论论文、反思协议、历史归档 | ✅ |

**数据流（简化）**：

```
OpenClaw 主代理（姐姐）
   │  每轮 prompt 注入（插件 qingruyan-behavior-enforcer）
   ▼
plugins/qingruyan-behavior-enforcer/index.js  ──读──►  /tmp/memory-trust.json（信任度加权）
   │  L0-L3 怀疑灯/幽灵决策/审查（DOUBT_L0 / GHOST_DECISION / L3_REVIEW）
   ▼
doubt.db（doubt_episode 账本 + memory_trust 表）──写──► 怀疑闭环
   ▲
night_patrol_run.sh（23:30 cron）──► night_patrol.py（汇总）──► 隔离子代理（时间旁观者）
   │                                                    └──► night_patrol_findings.py（回流写沙漏）
   │                                                    └──► /tmp/observer-alerts.json（警讯，插件按主题注入）
   └──► night_patrol_dogma.py（反教条复核）──► /tmp/observer-alerts.json
   └──► cross_review.py（跨实例互审，CROSS_REVIEW=1 启用）──► jiali 通道
```

---

## doubt-system/ —— 怀疑系统（自我怀疑 / 防回声室）

怀疑系统让 Agent OS 对自己的记忆与结论保持"可被推翻"：免费信号怀疑灯 → 幽灵决策 → 高风险审查 → 记忆信任度加权 → 夜巡旁观者回看当天 → 反教条复核 → 跨实例互审。

### 脚本一览

| 脚本 | 职责 |
|------|------|
| `memory_trust.py` | **记忆信任度数据层（P3.2）**：为每条记忆维护 `trust_weight = 1/(1+age_days) × (1 - rebuttal/(reference+1))`，被反驳 ≥2 次强制 0.1；数据存 doubt.db 的 `memory_trust` 表（不 ALTER 沙漏主表），重算后原子写 `/tmp/memory-trust.json` 供插件注入加权 |
| `test_memory_trust.py` | memory_trust 测试：引用/反驳/时效加权/强制降权/账本联动/JSON 输出/CLI，退出码 0=全通过 |
| `night_patrol.py` | **夜巡数据汇总器（P2.3/L4）**：汇总当天沙漏对话、memory 文件、operation_log FAIL、怀疑账本、topic_risk 到 `/tmp/night_patrol_input.json`（纯数据，不调 LLM） |
| `night_patrol_run.sh` | **夜巡执行器（23:30 cron）**：汇总 → 触发隔离子代理"时间旁观者"回看 → findings 回流 → 反教条复核 →（可选）跨实例互审；flock 单实例锁 + 每日幂等 marker，`--force` 强制重跑，`NIGHT_PATROL_DRY=1` 管道自检 |
| `night_patrol_findings.py` | **夜巡回流器**：校验隔离子代理产出的 findings（observer schema）→ 指纹去重 → 走官方 `sandglass_log.log_message` 写沙漏（tag=旁观者-警讯）→ severity≥4 且 confidence≥0.7 追加 `/tmp/observer-alerts.json`（flock 保护） |
| `night_patrol_dogma.py` | **反教条复核器（P3.3）**：挑出被引用最多的 top10 记忆（memory_trust 表按 reference_count 排序，降级走沙漏注入痕迹），注入"可能已过时"复核，每天 ≤3 条低频写沙漏 + 追加 `/tmp/observer-alerts.json`；年龄门槛默认 ≥30 天 |
| `cross_review.py` | **跨实例互审（P3.3）**：把关键决策摘要（脱敏）POST 到 `jiali.tdx1146.com:18888/api/inject` 让妹妹系统当旁观者，回传意见写沙漏（tag=旁观者-洞察，actor=cross-instance）；`--scan-only` 扫描最近 1h 回复 |

### 依赖关系（文件契约）

- **插件读**：`/tmp/memory-trust.json`（信任度加权，由 memory_trust.py 写）、`/tmp/observer-alerts.json`（警讯，由 night_patrol_findings.py / night_patrol_dogma.py 写，插件按主题匹配注入）
- **脚本读**：`/tmp/night_patrol_input.json`（夜巡子代理）、`/tmp/night_patrol_findings.json`（子代理产物）、`/tmp/topic_risk.json`（P2.4）、`/tmp/l3-review-request.json`（L3 审查请求，插件写）
- **脚本写**：`doubt.db`（doubt_episode 账本 + memory_trust 表，只由 memory_trust.py 写表）、沙漏（走官方 log_message 接口，不直写 SQLite）、`/tmp/observer-alerts.json`、`/tmp/memory-trust.json`
- **运行时注意**：`night_patrol_run.sh` 内含本机绝对路径（NEXSANDBASE_HOME、WORKSPACE、operation_log 路径），换机部署需按注释调整；脚本在 workspace/scripts 保留运行副本，本目录为版本管理副本。

---

## 三阶段部署与 L0-L5 五层模型

怀疑系统按三阶段（P1→P2→P3）分步上线，插件与脚本各管一层，全部通过环境变量 feature flag 控制开关。

| 阶段 | 层 | 能力 | 实现 | 启用方式 |
|------|----|------|------|----------|
| P1 | **L0 怀疑灯** | 5 类免费信号检测（矛盾/利害/FOK/惊讶/纠错），零 LLM 调用，输出动态区末尾 | 插件 index.js | `DOUBT_L0`（默认开，`=0/off/false` 关闭） |
| P2 | **L1 检索升级** | prefetch 异步化 + TTL 缓存 24h + 语义/BM25 混合 + 多样性防锚定 | 插件 index.js | 内置常开（v6.3+） |
| P2 | **L2 幽灵决策** | 决策场景检测 → entropy_ghost 幽灵决策（"如果选另一个选项会怎样"），TTL 24h/主题、日 ≤5 次 | 插件 index.js + 沙漏 `sandglass_dream` 工具 | `QINGRUYAN_GHOST_DECISION` |
| P3 | **L3 审查 + 信任度** | 高风险检测（不可逆操作/金额承诺/topic_risk≥4/连续否定 2 次）→ 子代理审查请求；记忆信任度加权注入 | 插件 index.js（`QINGRUYAN_L3_REVIEW`）+ `memory_trust.py`（数据层） | L3：`QINGRUYAN_L3_REVIEW=off` 关闭；信任度：`QINGRUYAN_MEMORY_TRUST` |
| P3 | **L4 时间旁观者 + 反教条** | 夜巡 23:30 隔离子代理回看当天找矛盾/模式/被忽略教训；反教条复核高频记忆"可能已过时" | `night_patrol_run.sh` + `night_patrol.py` + `night_patrol_findings.py` + `night_patrol_dogma.py` | 夜巡：crontab `30 23 * * *`；反教条：`QINGRUYAN_ANTI_DOGMA` |
| P3 | **L5 跨实例互审** | 关键决策脱敏摘要经 jiali 通道请妹妹系统当旁观者互审 | `cross_review.py` | `CROSS_REVIEW=1`（夜巡内联）；手动：`python3 cross_review.py --topic ... --options ... --tendency ...` |

### 三阶段回顾

1. **P1（v6.2, commit 9898f66）**：L0 怀疑灯 + 纠错→三元组教训
2. **P2（v6.3, commit 3ca88e7）**：L2 幽灵决策接线 + L1 检索升级（prefetch 异步化/TTL/混合检索）+ P2.4 topic_risk
3. **P3（v6.4, commit 36415a4）**：L3 审查请求 + 记忆信任度加权 + 反教条提示 + 本目录全部怀疑系统脚本（数据层/夜巡/反教条/跨实例互审）

### 快速验证

```bash
# 信任度数据层测试（需 living-memory-system venv）
/vol1/@apphome/trim.openclaw/data/home/agentos/living-memory-system/.venv/bin/python \
    /vol1/@apphome/trim.openclaw/data/workspace/scripts/test_memory_trust.py

# 夜巡管道自检（不调 LLM、不写 marker）
NIGHT_PATROL_DRY=1 /vol1/@apphome/trim.openclaw/data/workspace/scripts/night_patrol_run.sh

# 手动强制重跑夜巡
/vol1/@apphome/trim.openclaw/data/workspace/scripts/night_patrol_run.sh --force
```

---

## 相关文档

- `startup/README.md` —— 部署与启动全流程
- `startup/端口与服务.md` —— 服务端口清单
- `docs/meta-cognition/反躬自省/01-反思协议v0.5.md` —— 反思协议
- `docs/沙漏注入OpenClaw适配方案-2026-07-26.md` —— 沙漏注入适配方案
