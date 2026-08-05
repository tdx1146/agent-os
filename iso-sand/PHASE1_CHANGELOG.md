# PHASE1_CHANGELOG — 统一总线骨架

> 日期：2026-08-04
> 执行：总线工程师子AI（Phase 1：D1 原子写 + D3 迁回安全加固 + D7 契约三件套）
> 范围：仅修改 `/vol2/1000/AI专用/Agent OS/iso-sand/`（主总线 v0.4.1 → v0.6.0 加固）
> 基线备份（可回滚）：`/vol2/1000/AI专用/backups/phase0-baseline-20260804-165012/`

---

## 〇、改了什么（一句话）

把丰碑 fork（v0.6.0，已冻结）的**安全分派**（exec+script+EVENT_DATA+shell=False）和**原子写**移植回主总线，
并落地 D7 契约三件套（schema_version / event_type 注册表 / event_id 幂等去重 + trace_id 硬规范）。
主总线现在是"v0.4.1 功能 + v0.6.0 安全"的统一骨架。

## 一、改动清单

| 文件 | 改动 | 对应 |
|------|------|------|
| `src/log_writer.py` | 新增 `atomic_rewrite(lines)`（临时文件→fsync→os.replace 原子替换）+ `cleanup_stale_tmp()`（清理中断残留 .tmp）；**追加写保持不变**（append+flock+fsync 已满足原子语义，未改成 rename——对追加场景 rename 会覆盖丢数据） | D1 |
| `src/event_consumer.py` | ① `_filter_non_json_lines()` 从 `open("w")` 整文件重写改为**锁保护 + atomic_rewrite 原子替换**，重写后 seek 重置为 0（修 fork 已修的"首批事件被跳过"问题）；`_save_seek_offset()` 改为临时文件→os.replace 原子写 ② 移植 fork 的 `_dispatch_safe()`（exec+script，EVENT_DATA 环境变量传事件数据，shell=False 零注入面；exec 白名单仅 python/python3，PATH 找不到时回退当前解释器）；`_dispatch()` 优先走 exec+script，旧 command 模板保留为兼容路径（已废弃，打警告但仍可用）③ D7：`_load_processed_ids/_is_processed/_mark_processed`（event_id 幂等去重，内存集合 + data/processed_ids.jsonl 持久化）、缺失 trace_id 打 WARN 但继续处理、schema_version 缺失容忍默认 1.0 ④ quick_test 修复：原 `poll_loop()` 直接调用会**永久阻塞**（--test 会卡死），改为线程 start/stop 模式，并新增 D7 断言 | D1+D3+D7 |
| `src/task_scheduler.py` | 产出事件升级为 v1.1 契约：补 `schema_version: "1.1"` + `event_id`(UUID)，trace_id 原本已有（生产者侧契约合规；消费者侧向后兼容不拒绝） | D7 |
| `deploy/event_rules.yaml` | 3 条规则全部改写为 v0.6.0 exec+script 格式（语义不变）：rule-task-complete → script 内从 EVENT_DATA 取 trace_id 后 `subprocess.run([sys.executable, audit.py, "--event", trace_id], shell=False)`；rule-anomaly-escalate → 异常写 `/vol2/1000/AI专用/丰碑网络/data/alerts.log`；rule-audit-archive → 同理调 archive.py | D3 |
| `deploy/event_schema.yaml` | v1.0 → v1.1：`schema_version: "1.1"` 强制字段（老事件容忍默认 1.0）；`event_type` 注册表（核心 5 类 + 预留 xuanjian.pipe / lms.plastified / sandglass.heartbeat / interfaces.store 等命名空间，标注 Phase 2/4 启用）；`event_id`(UUID) 幂等去重规范；`trace_id` 从 optional 升级为硬规范（缺失 WARN 不拒绝）；兼容规则段落 | D7 |

## 二、为什么这么改（关键决策）

1. **追加不 rename、重写才 rename**：JSONL 追加场景 append+flock+fsync 已足够（崩溃最多丢最后半行，consumer 非 JSON 行清理兜底）；rename 用在**整文件重写**（清理非 JSON 行）防半写损坏——这是 D1 的核心语义，避免"一刀切 rename 丢数据"。
2. **安全分派优先，旧格式兼容**：新规则必须 exec+script（事件数据进环境变量，绝不进命令字符串）；老 command 规则仍可跑（经 `_check_shell_safe` 白名单），保证回滚/过渡期不炸。
3. **DATA_DIR 修正**：fork 的 `_dispatch_safe` 按 `丰碑/code/event_bus/` 布局推导 data 目录，直接移植到 iso-sand 会算出 `Agent OS/data`（不存在）；改为取消费者实际使用的 event 文件所在目录（`iso-sand/data`）。
4. **exec: "python" 在 Linux 可能不存在**：fork 只在 Windows 分支替换 sys.executable；移植时改为 PATH 找不到即回退当前解释器，规则统一用 `python3`。
5. **D7 去重语义**：只有带 event_id 的事件参与去重（老事件无 event_id 不拒绝、不参与）；处理完成（含未命中/死信）后标记，防 at-least-once 重投重复执行；processed_ids.jsonl 追加持久化，重启全量重载。
6. **quick_test 修复**：原代码 `consumer.poll_loop()` 在测试里无限阻塞，`--test` 从未真正通过；改为线程式验证（这也让验证项 1"quick_test 全过"从不可能变为可验证）。

## 三、D3 前置调研结论（fork vs 主，步骤 0）

| 文件 | fork(v0.6.0) 独有/差异 | 处置 |
|------|------------------------|------|
| `event_consumer.py` | `_dispatch_safe()`（exec+script+EVENT_DATA+shell=False）；`_filter_non_json_lines` 原子重写 + **seek 重置 0**；`_save_seek_offset` 原子写；`_event_writer` 锁；白名单含 `python` | **全部移植**（见改动清单） |
| `event_rules.yaml` | fork 有 9 条规则（task_complete OK/WARN/FAIL/TIMEOUT、milestone OK/WARN/FAIL、anomaly FAIL/WARN），主只有 3 条（task_complete/OK、anomaly/FAIL、audit_result/OK） | **3 条主规则改写为安全格式，语义不变**；fork 独有的 6 条**不移植**（任务要求保持原 3 条语义；额外规则属丰碑业务，Phase 2 接入时再评估） |
| `event_schema.yaml` | 两版相同（v1.0） | 升级 v1.1（D7） |
| `tasks.yaml` | fork 有 v0.5.0 真实任务 4 条（health_check/db_maintenance/freeze_check/periodic_sync），主**完全没有** tasks.yaml，且主 `task_scheduler.main()` 加载空任务 `[]` | **不移植**（路径指向 `{CODE_DIR}/core/*.py`，在 iso-sand 布局下会指向不存在的 iso-sand/core/，硬移植会造出必失败任务；属 Phase 2 D2/D5 范畴，报告中上报） |
| `log_writer.py` | fork 有日志轮转 `_maybe_rotate()` + Windows(msvcrt) 兼容 | **不移植**（本机 Linux 单机运行，轮转属丰碑运维特性；Phase 1 不做，报告中上报待决策） |

**结论**：fork 的**核心安全/可靠性增益**（安全分派、原子写、seek 修复）已全部移植；fork 独有的**业务规则与任务配置**未移植（不属于"骨架"，避免行为漂移）。

## 四、验证结果（步骤 4，逐项）

| # | 验证项 | 结果 |
|---|--------|------|
| 1 | `python3 src/event_consumer.py --test`（quick_test 全过，含 D7 断言） | ✅ PASS（修复前会卡死） |
| 1 | `python3 src/task_scheduler.py --test` | ✅ PASS（需 croniter，见遗留问题） |
| 2 | `_dispatch_safe` 冒烟：EVENT_DATA 传参断言、`"; touch /tmp/phase1_pwned #` 注入未执行、exec 白名单拒 bash、旧 command 兼容 | ✅ 4/4 |
| 3 | 原子写：atomic_rewrite 100 条→读回 100 条；子进程慢写 300MB 中途 SIGKILL → 主文件完好、留下 1 个 .tmp、cleanup_stale_tmp 清理、清理后重写正常 | ✅ 6/6 |
| 4 | 老事件重放：备份 v1.0 老事件（无 schema_version/event_id）→ 新 consumer 消费：无死信、operation_log OK×2、audit.py 桥接真实触发 | ✅ 4/4 |
| 5 | 幂等：同 event_id 投两次 → handler 只执行 1 次，processed_ids.jsonl 落盘 1 条 | ✅ 2/2 |
| 6 | 重启真实服务：stop_all.sh → 确认停净 → start_all.sh → 新 PID（scheduler 61502 / consumer 61507）→ 30s+ 日志无异常，tick/轮询正常 | ✅ |
| 6+ | 实机端到端：注入 v1.1 契约事件（schema_version+event_id+trace_id）→ 真实 consumer safe-mode 分派 → audit.py 写 audit_bridge.log → operation_log 记录 → processed_ids.jsonl 落盘 event_id | ✅ |

独立验证套件：`/tmp/phase1_verify.py`（17 项全过，PASS=17 FAIL=0）。

## 五、服务重启结果

- `stop_all.sh`：scheduler 34506 / consumer 34518 均已停止，无残留进程。
- `start_all.sh`：新 PID scheduler **61502** / consumer **61507**，均存活超过 1 分钟；consumer 加载 3 条新 exec+script 规则；scheduler tick 正常（17:02:24 / 17:02:54）；两日志无任何异常/死信。
- 注：start_all.sh 输出的 `verify_daemon ❌` 为**存量问题**（玄鉴守护进程未运行），与本阶段改动无关，Phase 2 处理。

## 六、如何回滚

1. 停止服务：`cd /vol2/1000/AI专用/Agent OS/iso-sand && bash stop_all.sh`
2. 从 Phase 0 基线恢复代码与配置（cp 覆盖）：
   - `cp -a /vol2/1000/AI专用/backups/phase0-baseline-20260804-165012/iso_sand_code/iso-sand/src/ /vol2/1000/AI专用/Agent OS/iso-sand/src/`
   - `cp -a /vol2/1000/AI专用/backups/phase0-baseline-20260804-165012/configs/iso-sand/event_rules.yaml /vol2/1000/AI专用/Agent OS/iso-sand/deploy/event_rules.yaml`
   - `cp -a /vol2/1000/AI专用/backups/phase0-baseline-20260804-165012/configs/iso-sand/event_schema.yaml /vol2/1000/AI专用/Agent OS/iso-sand/deploy/event_schema.yaml`
3. 数据文件可选回滚：`event_bus_data/iso-sand/` 下的 event_bus.jsonl / event_bus.seek / operation_log.jsonl（注意：会丢失本次改动后的增量记录）。
4. 重启：`bash start_all.sh`
5. 验证：`python3 src/event_consumer.py --test`、`python3 src/task_scheduler.py --test` 通过，日志正常。

## 七、遗留问题 / 已知限制

1. **croniter 依赖缺失**：系统 python3 无 croniter，`pip3 install` 被代理污染（sha256 校验失败，两次下载哈希不同）。已通过**直接 curl 下载 PyPI wheel 并校验官方 sha256** 后解压至用户 site-packages（`~/.local/lib/python3.11/site-packages`）解决：croniter 6.2.4 + python-dateutil 2.9.0.post0。**风险提示**：该代理异常值得关注（疑似透明代理篡改 pythonhosted 内容）；若换机器/换用户需重装。
2. **重写 vs 并发追加的跨进程竞态**（理论）：`_filter_non_json_lines` 的原子重写与其它进程（如 scheduler）的 append 并发时，若恰好交错可能丢少量追加行。fork 同样存在此问题（threading.Lock 仅同进程有效）。当前场景影响极小（清理只在启动时、scheduler 现无任务）；Phase 2 建议引入文件锁协议（如独立 .lock 文件）彻底解决。已在代码注释标明。
3. **processed_ids.jsonl 无上限增长**：内存集合上限 100k（超限仅内存暂停增长、文件仍追加），文件本身会持续增长；Phase 2 建议加定期压缩（只保留最近 N 天）。
4. **fork 独有特性未移植**（待 dandan 决策）：日志轮转 `_maybe_rotate()`、fork 的 9 条业务规则、tasks.yaml 真实任务配置。
5. **幂等窗口**：处理与落盘之间崩溃会丢失已处理标记 → 极端情况下重投可能重复执行一次（at-least-once 语义内，非新增问题）。
6. **验尸记录**：本次注入的 1 条测试事件（`phase1-live-test-001`）保留在 event_bus.jsonl 作为实机验证痕迹，与 7 月 deploy_verify 事件同性质。

## 八、安全红线遵守

- ✅ 未修改 iso-sand 之外任何代码（audit.py/archive.py 仅被调用，未改动；丰碑 fork 目录未动）
- ✅ 未删除 fork 代码（D3 为"冻结+移植"）
- ✅ 无任何 git push/commit
- ✅ 未打印任何 token/密钥
