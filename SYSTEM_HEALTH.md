# SYSTEM_HEALTH.md — 全系统健康巡检手册（dandan 用）

> 2026-08-10 建立。目标：**不用凭感觉、不用天天问——一条命令看全系统死活，cron 每 30 分钟自动巡检，坏了才喊。**
> 巡检脚本：`Agent OS/scripts/system_health_check.sh`（只读，不碰任何系统状态）
> 本文件配套 SYSTEM.md §6（3 分钟巡检法的手动版 → 本文件是自动化版）。

---

## 1. 怎么用（一句话）

```bash
cd "/vol2/1000/AI专用/Agent OS" && bash scripts/system_health_check.sh
```

- 全绿 ✅ → 退出码 0；有警告 ⚠️ → 1；有故障 ❌ → 2
- 末尾是汇总表：**组件 | 状态 | 关键数字**
- 想留档/告警：`bash scripts/system_health_check.sh --cron`（cron 用，见 §4）

---

## 2. 每项健康信号的含义（人话）

| 巡检项 | 看什么 | 绿 = | 红 = |
|--------|--------|------|------|
| **沙漏API** | `:17333/api/health` | 端口活着，sandglass_count 有数 | 沙漏进程死了（明线全断） |
| **沙漏落沙** | `sandglass.txt` 最后写入时间 | 30 分钟内有过新落沙 | 6 小时无新增（明线断=失忆根源） |
| **沙漏索引** | `sandglass.idx` mtime | 1 小时内更新过 | 2 小时停更（检索退化） |
| **沙漏自治** | `metrics.jsonl` mtime | 15 分钟内更新（self_pulse 每 10min 写） | 30 分钟停更（落沙管线/self_pulse 断） |
| **显著性/体力** | `salience_state.json` + `sleep_pressure.json` | 都在 15 分钟内更新，体力模式可见 | 停更（唤醒链的闸门死了） |
| **怀疑账本** | `doubt.db` mtime | 48 小时内有写入 | 7 天没写（怀疑系统停摆） |
| **LMS-API** | `/health` + `/status/main` | 轮次/惊讶/熵比/目的都正常，惊讶 ≥ 0 | 端口不可达；惊讶 < 0 = 降级语义 |
| **LMS-深度指标** | `logs/lms_metrics.jsonl` mtime | 30 分钟内更新 | 停更 → **深度健康检查 cron 没了**（历史上停过 22h） |
| **LMS-告警账本** | `logs/lms_alerts.jsonl` 最近 24h | 无 CRIT/WARN | 有备份失败等告警记录（看时间戳判断新旧） |
| **LMS-控制口** | `:8191` 监听 | 在听 | 没监听（控制指令不可达，@reboot 没触发） |
| **胶水层** | `:19000/health` 三后端 | sandglass/lms/vector 全 healthy | 任一后端坏（读侧断=AI 失忆） |
| **总线** | `event_bus.jsonl` + `operation_log.jsonl` + scheduler/consumer PID | 10 分钟内都有新事件，两个进程活着 | 停更/进程死（调度器或消费者死了） |
| **玄鉴-进程** | daemon.pid + `daemon_audit.log` | 5 分钟巡检在跑 | 停更（监督死了） |
| **玄鉴-审计发现** | audit 日志里 FAIL/WARN 数 | 近 200 行 0 FAIL | FAIL 多 = 有真实异常（如 git 推送未落地） |
| **夜巡** | `workspace/logs/night_patrol.last_run` marker | 昨天/今天有成功标记 | 无 marker = 夜巡从没跑成（crontab 空格拆词 bug） |
| **self_pulse** | `/tmp/pulse-status.json` + 4 个唤醒链脚本 | 15 分钟内更新且 rc=0 | 停更（唤醒链断，AI 不会自主醒来） |
| **回魂插件** | `/tmp/glue-hook-debug.log` | 7 天内有 INJECTED | 一周没注入（读侧断=每轮失忆） |
| **备份** | `lms_backup_cron.log` + 最新快照 | 无近期 ERROR，快照 30 分钟内 | 快照 2 小时没更新或日志有 ERROR |
| **cron完整性** | crontab 关键条目 | 三把锁+备份+深度健康+巡检都在 | 缺条目（列出缺谁） |
| **磁盘** | `/vol2` 使用率 | < 90% | ≥ 95% |

---

## 3. 故障了怎么办（对号入座）

| 红色项 | 先看哪 | 大概率原因 | 处置 |
|--------|--------|-----------|------|
| ❌ 沙漏API / 沙漏落沙 | `Agent OS/logs/sandglass_http_api.log` | 沙漏进程死了 | `bash start_all.sh`（幂等重启） |
| ❌ 沙漏自治 / 显著性/体力 | crontab 里 `pulse-cron.sh` 还在不在 | self_pulse cron 被覆盖 | 补 `*/10 * * * * .../pulse-cron.sh` |
| ❌ LMS-API | `living-memory-system-cloud/logs/lms_api.log` | LMS 进程死了 / `.env` 没 source | `bash scripts/lms_ctl.sh start`（先 source .env） |
| ❌ LMS-深度指标 | crontab 里有没有 `lms_ops_monitor.py` | **深度健康检查 cron 缺失**（当前真实病灶） | 加 cron，见 §5 修复 1 |
| ❌ 胶水层 | `Agent OS/logs/glue_server.log` + 三后端各自 health | LMS/沙漏/向量挂了会带崩它 | 先救后端，再 `bash start_all.sh` |
| ❌ 总线 | `iso-sand/data/scheduler.pid` `consumer.pid` | 调度器/消费者死了 | `bash iso-sand/start_scheduler.sh` + `start_consumer.sh` |
| ❌ 玄鉴-进程 | `xuanjian/data/daemon.pid`（2026-08-12 起玄鉴并入 agent-os/xuanjian；本机运行实例暂在旧同构沙盘 data/） | verify_daemon 死了 | 重跑 `src/verify_daemon.py` |
| ❌ 玄鉴-审计发现 | audit 日志 FAIL 行的 detail | git 推送没落地（见 §6 现状③） | `git status` 查 ahead，push 补推 |
| ❌ 夜巡 | `/tmp/night-patrol-cron.log` | **crontab 路径含空格被拆词 + 脚本内路径错**（当前真实病灶） | 见 §5 修复 2 |
| ❌ 备份 | `living-memory-system-cloud/logs/lms_backup.log` | rsync/磁盘/锁 | 看 ERROR 行；`bash scripts/lms_backup.sh --quick` 手动跑一次 |
| ❌ 磁盘 | `df -h /vol2` | 空间满 | 清旧备份（hourly 保留 9 份、daily 保留策略） |

**通用心法：** 红→黄→绿 是「进程死了 → 数据停更 → 全好」三级；看到红先看对应进程，看到黄先看对应 cron。

---

## 4. 自动告警（cron 接入，供 dandan 确认后添加）

**机制：** 每 30 分钟跑一次，全量结果追加到 `Agent OS/logs/system_health.log`；
**只有状态变化才写告警行**（绿→黄/红 写 🚨，恢复写 ✅），不刷屏。

```crontab
# ===== 全系统健康巡检（2026-08-10 新增，路径含空格必须加引号）=====
*/30 * * * * bash "/vol2/1000/AI专用/Agent OS/scripts/system_health_check.sh" --cron >> "/vol2/1000/AI专用/Agent OS/logs/system_health.log" 2>&1
```

- 状态基线存在 `Agent OS/run/system_health.state`（首次运行只建基线不告警）
- 告警示例：`🚨 [2026-08-10 23:33:30] [夜巡] 故障: marker 不存在——...`
- 后续接消息推送：只需把日志里的 🚨 行转发到聊天（本次只做日志机制）
- 查历史：`tail -50 "/vol2/1000/AI专用/Agent OS/logs/system_health.log"`

---

## 5. 建议同时修的三个已知病灶（巡检发现的，dandan 确认后执行）

### 修复 1：LMS 深度健康检查 cron 缺失（lms_metrics.jsonl 已停更 23h）
```crontab
# 深度健康检查（L1 30s / L2 60s / L3 5min 三级，写 lms_metrics.jsonl + lms_alerts.jsonl）
*/5 * * * * cd "/vol2/1000/AI专用/living-memory-system-cloud" && python3 scripts/lms_ops_monitor.py >> logs/lms_ops_monitor.log 2>&1
```

### 修复 2：夜巡 cron 路径空格拆词 + 脚本内路径错（夜巡从未跑成）
crontab 行改为加引号：
```crontab
30 23 * * * bash "/vol2/1000/AI专用/Agent OS/doubt-system/night_patrol_run.sh" >> /tmp/night-patrol-cron.log 2>&1
```
另外 `night_patrol_run.sh` 内部 `SCRIPTS="$WORKSPACE/scripts"` 指向了 workspace/scripts，
但 `night_patrol.py` 实际在 `Agent OS/doubt-system/`——需要把 SCRIPTS 指对（或软链），否则引号修好仍会失败。

### 修复 3：LMS 控制口 :8191 未监听（@reboot 是机器重启后才生效的，已 up 6 天）
```bash
cd "/vol2/1000/AI专用/living-memory-system-cloud" && setsid .venv/bin/python scripts/run_control.py --host 127.0.0.1 --port 8191 >> logs/lms_control.log 2>&1 < /dev/null &
```

---

## 6. 当前现状快照（2026-08-10 23:33 实测）

**全绿 14 项：** 沙漏全链（API/落沙/索引/自治/显著性体力/怀疑账本）、LMS-API、胶水层、总线、玄鉴-进程、self_pulse、回魂插件、备份、磁盘。

**3 红 3 黄（都是真问题，非误报）：**

| 项 | 状态 | 证据 | 性质 |
|----|------|------|------|
| LMS-深度指标 | ❌ | lms_metrics.jsonl 停更 23h | 深度健康检查 cron 丢失（修复 1） |
| 玄鉴-审计发现 | ❌ | 近 200 行 FAIL=44（push_verify：LMS 仓库 ahead=2 未推送 d5f7638/0f90bb3） | git 推送未落地（§5 修复 3 之外，需 push） |
| 夜巡 | ❌ | marker 不存在，从未成功 | crontab 空格拆词 + 脚本路径错（修复 2） |
| LMS-告警账本 | ⚠️ | 24h 内有 CRIT：8/10 16:30 备份失败（--quick rc=1） | 历史告警，16:30 后备份已恢复全绿，明天自动转绿 |
| LMS-控制口 | ⚠️ | :8191 未监听 | @reboot 未触发（机器 6 天没重启）（修复 3） |
| cron完整性 | ⚠️ | 缺 lms_ops_monitor.py + system_health_check.sh | 修 1 + 加本巡检 cron 后转绿 |

---

## 7. 3 分钟巡检法（升级版 · 自动化之前的临时方案）

> 不想跑脚本、只想扫一眼时的极简版（比 SYSTEM.md §6 多了「深度指标」和「夜巡」两个最容易漏的）：

```bash
cd "/vol2/1000/AI专用/Agent OS"
bash status_all.sh                                 # ① 6 服务进程/端口全绿？
tail -2 "所有自动化/轻如烟/sandglass/metrics.jsonl" # ② 明线：尾部是 10 分钟内？（自治脉冲）
curl -s :8190/status/main | head -c 200             # ③ 暗线：轮次/惊讶在涨？
tail -2 iso-sand/data/event_bus.jsonl              # ④ 总线：尾部是当前？
tail -3 /tmp/glue-hook-debug.log                   # ⑤ 胶水：最近对话有 INJECTED？
ls -la logs/lms_metrics.jsonl                      # ⑥ 深度指标：今天有更新？
ls workspace/logs/night_patrol.last_run            # ⑦ 夜巡：昨天/今天有 marker？
```

**一句话判定：** ①全绿 + ②③⑥是今天 + ④是当前 + ⑤有 INJECTED + ⑦有 marker = 系统活着。
任何一项不是 → 对号入座 §3 表格。

---

*维护规则：新增组件/改端口 → 同步改本文件 §2 表 + 脚本对应 check 段；巡检脚本本身零硬编码（路径全部来自 env.local 或相对推导）。*
