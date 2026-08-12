# SELF_PULSE_README — self_pulse 真任务化设计文档（2026-08-05）

> 配套文件：`self_pulse_cli.py`（v2）、`pulse-cron.sh`、
> 待办源 `/vol1/@apphome/trim.openclaw/data/workspace/memory/backlog.md`
> （backlog.md 相关说明见下文"待办源契约"）。

## 1. 背景

self_pulse（沙漏自治脉冲）设计意图：每 10 分钟自主"醒来"，读待办推进 /
无待办时做画像漂移检查。Phase6 重建后一直在"测试模式"：
- 待办源 `workspace/memory/backlog.md` 不存在 → 永远走守夜感知分支
- 画像漂移检查只写一句话，没有任何检查逻辑
- 每 10 分钟一条"🌫️ self_pulse round N: 守夜感知…"刷屏 sandglass.txt，
  已被回魂过滤逻辑判定为噪音

v2 把两个真任务做成真逻辑，并做输出分级噪音治理。

## 2. 画像漂移检查（真逻辑，规则可解释）

### 采集（全只读、fail-open）
| 来源 | 字段 | 用途 |
|------|------|------|
| LMS `/status/main`（127.0.0.1:8190，timeout 3s） | entropy_ratio / purpose_coherence / last_surprise / turn_count | 判定主指标（curl 实测字段名） |
| 沙漏近期记忆（sandglass.txt 尾部 3 行） | — | 告警叙事上下文（只用于 alert payload） |
| 自身上次脉冲状态（/tmp/pulse-state.json） | last_5 / streaks / drift | 连续计数与去重游标 |

### 指标选择理由
- **entropy_ratio**：LMS 吸引子景观的归一化熵，表征记忆状态是否涣散；
  LMS 自身即维护 `entropy_high_threshold=0.9`（/status 实测返回），
  用系统自定义的高熵线做阈值，不自造常数。
- **purpose_coherence**：目的层一致性，表征"我还在做该做的事"；
  实测健康区间 0.85–0.95（当前 0.92）。
- **last_surprise / turn_count**：辅助上下文，进快照与 metrics 供回溯，
  不参与判定。

### 判定阈值依据（保守起步）
| 规则 | 阈值 | 依据 |
|------|------|------|
| 高熵漂移 | entropy_ratio > 0.9 连续 ≥3 次 | 0.9 = LMS 自身高熵线；连续 3 次 ≈ 30 分钟持续高熵（10 分钟一拍），单次尖峰（如做梦周期）不误报 |
| 目的漂移 | purpose_coherence < 0.8 连续 ≥3 次 | 任务给定阈值；与健康区间（0.85–0.95）留 ~0.1 裕量，先保守后收紧 |
| 无法测量 | 指标缺失（LMS 不可达）→ 计数归零 | fail-open：宁可漏报不可误报；"连续"严格指可测量的连续脉冲 |

### 边沿触发告警（防刷屏）
仅 **正常→漂移 转换** 时发一条告警（sandglass ⚠️ + 总线 anomaly）；
漂移持续期（streak ≥ 3 继续累计）不重复发；恢复后再漂移重新告警。
→ 一个漂移 episode 至多一条告警，总线与叙事层都不会被刷。

## 3. 输出分级（噪音治理）

| 状态 | metrics.jsonl | sandglass.txt | 事件总线 |
|------|---------------|---------------|----------|
| 正常（无漂移、无新待办） | ✅ 一行指标快照 | ❌ 不写 | — |
| 漂移（转换触发） | ✅ | ✅ `⚠️ self_pulse 漂移告警: …` | `anomaly`/FAIL（走 alert.anomaly handler → 丰碑 alerts.log） |
| 新待办（hash 变化） | ✅ | ✅ `self_pulse 待办提醒: …` | `alert.todo`/OK（暂无 handler，总线留痕） |

**为什么正常态不写 sandglass.txt**：sandglass.txt 是叙事层，被回魂/召回
读取；每 10 分钟一条"我醒了"无叙事价值，已被回魂过滤判为噪音。
例行遥测归 metrics.jsonl（指标层），sandglass 只保留值得叙事的内容
（告警/新待办）。这正是"正常 → 只写 metrics"的设计理由。

## 4. 待办源契约（backlog.md）

- 位置：`/vol1/@apphome/trim.openclaw/data/workspace/memory/backlog.md`
- 来源（顶部注释注明）：① dandan 指令 ② 审计/复盘发现 ③ 总线事件沉淀
- 格式：`- [ ] 描述` / `- [x] 描述`；self_pulse 取第一条未完成项
- 去重：`last_todo_hash` 游标（状态文件）——同一待办只提醒一次，
  变更/新增才再次提醒（防每 10 分钟重复刷）
- 初始为空清单（骨架已建，文件缺失时 fail-open 视为无待办）

## 5. 状态与轮次

- 状态：`/tmp/pulse-state.json`（近 5 次快照 + streaks + drift + last_alert
  + last_todo_hash；原子写 tmp+rename）
- 轮次：`/tmp/self_pulse_round.txt` 机制沿用（1..5 递增到顶重置，
  `SELF_PULSE_MAX_ROUNDS=5`）；v2 到顶不再写"已达最大轮次"噪音行
- 环境变量兼容：`NEXSANDBASE_HOME` / `SELF_PULSE_MAX_ROUNDS` 不变；
  新增可选：`SELF_PULSE_LMS_URL` / `SELF_PULSE_BUS_FILE` /
  `SELF_PULSE_STATE_FILE` / `SELF_PULSE_ENTROPY_HIGH` /
  `SELF_PULSE_PURPOSE_LOW` / `SELF_PULSE_MIN_STREAK`

## 6. 测试方法（dry-run 零写入）

```bash
# 正常态演练（应：只计划写 metrics，不写 sandglass、不发总线）
python3 self_pulse_cli.py --dry-run

# 高熵漂移演练（预载 2 次高熵状态 + 本次模拟高熵 → 第 3 次触发告警）
cat > /tmp/pulse-state-fixture-high.json << 'EOF'
{"last_5": [{"entropy_ratio": 0.95}, {"entropy_ratio": 0.94}],
 "streaks": {"high_entropy": 2, "purpose": 0},
 "drift": {"high_entropy": false, "purpose": false},
 "last_todo_hash": "", "last_todo": ""}
EOF
python3 self_pulse_cli.py --dry-run --simulate high_entropy \
    --preload-state /tmp/pulse-state-fixture-high.json

# 真实写入路径隔离测试（全部落到 /tmp 测试文件，不碰生产文件）
python3 self_pulse_cli.py --simulate high_entropy \
    --preload-state /tmp/pulse-state-fixture-high.json \
    --state-file /tmp/test-state.json --bus-file /tmp/test-bus.jsonl \
    --round-file /tmp/test-round.txt \
    --metrics-file /tmp/test-metrics.jsonl --sand-file /tmp/test-sand.txt
```

## 7. 回滚

- v1 行为（每脉冲写 sandglass.txt）仅被新逻辑替代；轮次/环境变量兼容，
  旧 crontab 条目无需改动
- 备份：`/vol2/1000/AI专用/backups/selfpulse-20260805/`
- 本目录已 git init（分支 main），本次改动已提交；`git log` 可回看
