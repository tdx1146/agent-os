# PHASE2_CHANGELOG — handler 注册表 + 调度器接真实任务 + 拓扑工具（调整版）

> 日期：2026-08-04
> 执行：总线工程师子AI（Phase 2 调整版：D6 handler 机制 + 调度器接任务 + 拓扑工具 + verify_daemon 评估）
> 范围：仅修改 `/vol2/1000/AI专用/Agent OS/iso-sand/`（主总线 v0.6.0 → v0.7.0）
> 重要调整：**D2（玄鉴接入主总线）已延后**——本次只做注册表预留（`xuanjian.pipe` 占位 handler），不实施 D2
> Phase 2 基线备份（回滚用）：`/vol2/1000/AI专用/backups/phase1-baseline-20260804-171425/`
> 终极回滚（含 Phase 1 回退）：`/vol2/1000/AI专用/backups/phase0-baseline-20260804-165012/`

---

## 〇、改了什么（一句话）

落地 D6 统一 handler 机制（`src/handlers.py`：注册表 + 生命周期 + 异常隔离），消费者 handler 链优先、旧 rules 兼容回退；
调度器从 `deploy/tasks.yaml` 加载真实任务（替换硬编码空列表），接入心跳任务解决空转；
新增事件拓扑工具（`src/topology.py`，含环状订阅检测）；verify_daemon 只读评估（不改不启）。

## 一、改动清单

| 文件 | 改动 | 对应 |
|------|------|------|
| `src/handlers.py` **新增** | ① `Handler` 抽象基类：`handle(event)->bool` + `load()/unload()` 生命周期钩子 + `results` 过滤 + 独立 `rate_limit` ② `HandlerRegistry`：按 event_type 注册（一类型多 handler）、按注册顺序执行、**异常隔离**（单个 handler 抛异常/返回 False → 记死信，继续下一个，不拖垮消费循环）、`load_all()/unload_all()`、限流 ③ 内置 4 handler：`audit.task_complete`（等价 rule-task-complete，调 丰碑 audit.py --event，shell=False 数组传参）、`alert.anomaly`（等价 rule-anomaly-escalate，写 丰碑 data/alerts.log JSON 行）、`archive.audit_result`（等价 rule-audit-archive，调 archive.py）、`xuanjian.pipe`（玄鉴预留占位，D2 延后 no-op 仅记录）④ `quick_test()` 单元自测（注册/重复拒绝/异常隔离/死信/result 过滤/限流/注销/生命周期） | D6 |
| `src/event_consumer.py` | ① `__init__` 构建默认 handler 注册表并 `load_all()`（`enable_handlers=False` 可关，供封闭自测）② `_process_event` 重构：**先查 HandlerRegistry，有注册 handler 走 handler 链，没有回退旧 rules**（互斥不双跑）；规则循环抽为 `_dispatch_rules()`，新增 `_dispatch_handler_chain()` ③ 启动日志显示 handler 注册表数量 | D6 |
| `src/task_scheduler.py` | ① 移植 fork 的 `_load_tasks_from_yaml()`（占位符 {CODE_DIR}/{SRC_DIR}/{DEPLOY_DIR}/{DATA_DIR}/{BASE_DIR}，schedule→cron，**目标脚本存在性校验**——不存在 WARN 并跳过不接）② `main()` 从 tasks.yaml 加载（默认 deploy/tasks.yaml），支持 `--tasks-file` ③ `TaskScheduler.__init__` 支持 `tasks_file` 参数直接加载 | 任务 2 |
| `deploy/tasks.yaml` **新增** | 主调度器任务配置：`bus_heartbeat`（`*/5 * * * *`，调 deploy/heartbeat.py）——fork 的 4 条丰碑任务全部不接入（原因见 §三） | 任务 2 |
| `deploy/heartbeat.py` **新增** | 心跳任务脚本：向主总线写 `sandglass.heartbeat` 事件（v1.1 契约：schema_version/event_id/trace_id），经 LogWriter 线程+进程锁写入 | 任务 2 |
| `src/topology.py` **新增** | 扫描 event_schema.yaml + handlers.py 注册表 + event_rules.yaml，输出「谁产生 → 谁消费」文本拓扑；环状订阅检测（长度≥2 的 A→B→A 输出 WARN，自环单列 INFO）；`--json` 输出；一致性检查（未注册事件类型/孤儿事件 WARN，预留命名空间 INFO）；CLI：`python3 src/topology.py` | 任务 3 |
| `src/__init__.py` | v0.4.1 → v0.7.0，导出 Handler/HandlerRegistry/build_default_registry/TopologyAnalyzer | — |
| `start_scheduler.sh` | 生成的 runner 从 `load_tasks([])` 改为 `tasks_file=deploy/tasks.yaml`（解决生产空转） | 任务 2 |

## 二、为什么这么改（关键决策）

1. **handler 链与 rules 互斥（按 event_type 分流）**：有注册 handler 的事件类型只走 handler 链，rules 不跑——避免 task_complete 被 handler + rule 双执行（audit 跑两次）。rules 仅对无 handler 的事件类型生效（兼容回退）。旧 3 条 rules 保留不删（兼容期），文档注明"新子系统接入 = 注册 handler，不再改 rules"。
2. **handler 语义等价实现**：3 个内置 handler 的动作与 Phase 1 规则脚本逐字等价（audit.py/archive.py 用 `[sys.executable, ...]` 数组传参 + shell=False；alerts.log 写同样的 JSON 结构）；rate_limit 与规则一致（1.0/5.0/2.0）。**唯一差异**：handler 单次执行不重试（旧规则 3 次指数退避）——异常隔离优先于重试，失败即死信（含 handler 名与异常信息），权衡已记录于遗留问题。
3. **heartbeat 证明调度器活着**：调度器从空列表 → 1 条心跳任务；每 5 分钟写 `sandglass.heartbeat`（v1.1 契约）。该事件无 handler/rule（仅观测信号，与 schema 中 sandglass.heartbeat 的"仅观测不统合"定位一致），消费者"无匹配"但完成 seek/去重——证明整条链路活着。心跳任务自身产生 task_complete/OK → 会触发 audit.task_complete（每 5 分钟一条 audit_bridge.log 记录，低噪音，audit.py 无副作用仅追加日志，可接受）。
4. **tasks.yaml 命令带引号**（`python3 '{DEPLOY_DIR}/heartbeat.py'`）：iso-sand 路径含空格（`Agent OS`），shell=True 下裸路径被空格截断（首跑实测 FAIL，stderr 可见）；加引号后 OK。loader 的目标存在性校验对引号路径剥离引号后再判。
5. **`enable_handlers=False` 供自测**：consumer quick_test 原本依赖"anomaly/FAIL 无匹配规则"断言，内置 alert.anomaly 注册后会真写丰碑 alerts.log（自测副作用 + 断言破坏）；开关让自测封闭（仅 rules 路径），handler 链单独由 handlers.py quick_test 覆盖。
6. **拓扑环检测口径**：自环（A→A，如 xuanjian.pipe 占位自观察）不判为有害环（INFO 单列）；长度≥2 的 A→B→A 才 WARN（R2 红线）。当前拓扑无环。

## 三、fork tasks.yaml 审查结论（任务 2）

fork `/vol2/1000/AI专用/丰碑网络/code/event_bus/tasks.yaml` 共 4 条任务，逐条审查：

| id | cron | command（{CODE_DIR}=丰碑网络/code） | 目标文件 | 存在? | 结论 |
|----|------|------------------------------------|----------|-------|------|
| health_check | `*/10 * * * *` | `python3 {CODE_DIR}/core/health_checker.py` | 丰碑网络/code/core/health_checker.py | ✅ 存在 (25KB) | **不接入** |
| db_maintenance | `0 3 * * *` | `python3 {CODE_DIR}/db/database.py` | 丰碑网络/code/db/database.py | ✅ 存在 (5.4KB) | **不接入** |
| freeze_check | `0 */6 * * *` | `python3 {CODE_DIR}/core/freeze_detector.py` | 丰碑网络/code/core/freeze_detector.py | ✅ 存在 (14KB) | **不接入** |
| periodic_sync | `*/30 * * * *` | `python3 {CODE_DIR}/core/periodic_syncer.py` | 丰碑网络/code/core/periodic_syncer.py | ✅ 存在 (11.5KB) | **不接入** |

**跳过原因**（目标文件在丰碑布局下其实存在，但接入主总线不合理）：
1. 这 4 条是**丰碑域任务**，fork 自己的调度器已实现同样的 tasks.yaml 加载器（`_load_tasks_from_yaml`，v0.5.0）；主总线再接入 = **两个调度器可能同时跑同一批维护任务**。db_maintenance 跑 database.py（迁移/清理），双跑有真实风险。
2. 按 iso-sand 布局解析 {CODE_DIR} → `iso-sand/core/*.py` **不存在**（loader 目标校验会跳过）——与任务书"指向不存在文件的跳过不接"规则一致。
3. 丰碑接入属 Phase 2 **D5（monument_bridge）** 范畴，不在本阶段；安全红线"不碰丰碑"。
4. 接入替代：**bus_heartbeat 心跳任务**（沙漏式存活证明），已实机验证。

## 四、verify_daemon 状态评估（任务 4，只读，未改动）

对象：`/vol2/1000/AI专用/AgentOS-IsoSand/同构沙盘/src/verify_daemon.py`（v0.1，玄鉴守护进程）

- **校验什么**：监控 `同构沙盘/data/operation_log.jsonl` 新条目 → 从 detail 正则提取文件名（src/docs/tests/... 路径）→ `git diff --stat` 对照 → 关键词重叠度（>0.5 PASS / ≥0.2 SUSPECT / <0.2 FAIL）→ 写 `daemon_audit.log`；连续 3 次 FAIL 追加 WARN 回 operation_log；每 ~5 分钟对 `内核层规范/PURPOSE.md` 做 sha256 完整性检查（对照 purpose.sha256）。
- **依赖**：Python 3.11 标准库（无第三方）+ git（同构沙盘是 git 仓库）+ `内核层规范/`（PURPOSE.md + snapshots，均存在）+ 自身 data/（pid/seek/audit 文件齐全）。
- **为什么没在跑**：机器 **08-04 14:48 重启**；verify_daemon **无任何自启机制**（手动 `python3 src/verify_daemon.py &` 启动；无 systemd 单元、无 @reboot、无 crontab 条目，deploy/cron_tasks.json 的唯一任务 `initially_enabled: false`）；被重启杀死后无监督拉起。daemon.pid 过期（3183279，进程已死）；daemon.log 空（从不写 stdout）；daemon_audit.log 最后写入 12:51（重启前，其后无 shutdown 记录——被 kill 无优雅退出）。被监控的 operation_log 自 07-16 起无新条目（seek==size 无堆积）。
- **恢复成本**：极低（约 1 分钟）——`nohup python3 src/verify_daemon.py >> data/daemon.log 2>&1 &`（或加进 start_all.sh），清掉过期 pidfile 即可；依赖全在，零安装。
- **恢复收益**：当前很小——校验对象（IsoSand operation_log）已闲置 3 周，D2（玄鉴）又延后，跑起来也只是空转值守。
- **建议（供 dandan 决策）**：**暂不恢复**，等 IsoSand/玄鉴活跃后再花 1 分钟接回（届时建议纳入 start_all.sh 统一监督）。另发现：原 30 分钟级健康检查 cron（zhaojian-monitor，写 daemon_audit.log 的那条）重启后也未再写入（最后 12:51），**来源未在当前用户 crontab 定位到**，若属系统级 cron 需另行排查——这是唯一需要留意的运维盲点。

## 五、验证结果（逐项）

| # | 验证项 | 结果 |
|---|--------|------|
| 1 | handlers.py 单元测试：注册/重复拒绝/执行链/**异常隔离（bad 抛异常，good 仍执行，false 记失败）**/死信含异常信息/result 过滤/限流/注销/生命周期 | ✅ PASS（`python3 src/handlers.py`，8 组断言全过） |
| 1 | 环检测单元测试：A→B→C→A + X→Y→X 检出、无环图返回空 | ✅ PASS |
| 2 | 端到端：注入 v1.1 事件 task_complete/OK → handler 链 → audit.py → `丰碑网络/code/data/audit_bridge.log` 新增 `e2e-phase2-001`；anomaly/FAIL → alerts.log 新增 `e2e-anomaly-001`；audit_result/OK → archive_bridge.log 新增 `e2e-archive-001`（新文件创建）；xuanjian.pipe → 占位 handler 记录；operation_log 4 条 handler 链 OK 记录；死信 0 条；processed_ids 全部落盘 | ✅ PASS |
| 3 | 调度器：重启后 **1s 内**（首个 tick 17:18:01）产生 sandglass.heartbeat + task_complete/OK 两条任务事件 → 消费者消费：heartbeat 无匹配（预期）、task_complete 走 handler → audit_bridge.log 新增 `task-bus_heartbeat-*` | ✅ PASS（60s 要求满足） |
| 4 | 拓扑工具：`python3 src/topology.py` 输出含 `xuanjian.pipe` 预留命名空间 + 3 内置 handler + 玄鉴占位 + 环检测 **✅ 无环**（core→audit/alert/archive，xuanjian 自环 INFO） | ✅ PASS |
| 5 | 重启真实服务：stop_all.sh → start_all.sh → 新 PID（scheduler 68053 / consumer 68058）→ 日志无异常（grep ❌/Traceback/ERROR = 0），dead letter 0 字节 | ✅ PASS |
| 6 | 失败回滚：未触发；回滚路径见 §六 | — |

## 六、回滚指引

```bash
# Phase 2 回滚（恢复到 Phase 1 状态，含 src/deploy/启动脚本/data）
rm -rf "/vol2/1000/AI专用/Agent OS/iso-sand/src" \
       "/vol2/1000/AI专用/Agent OS/iso-sand/deploy"
cp -a /vol2/1000/AI专用/backups/phase1-baseline-20260804-171425/src \
      /vol2/1000/AI专用/backups/phase1-baseline-20260804-171425/deploy \
      /vol2/1000/AI专用/Agent OS/iso-sand/
cp -a /vol2/1000/AI专用/backups/phase1-baseline-20260804-171425/start_all.sh \
      /vol2/1000/AI专用/backups/phase1-baseline-20260804-171425/start_scheduler.sh \
      /vol2/1000/AI专用/backups/phase1-baseline-20260804-171425/start_consumer.sh \
      /vol2/1000/AI专用/backups/phase1-baseline-20260804-171425/stop_all.sh \
      /vol2/1000/AI专用/Agent OS/iso-sand/
bash /vol2/1000/AI专用/Agent\ OS/iso-sand/stop_all.sh && bash /vol2/1000/AI专用/Agent\ OS/iso-sand/start_all.sh
# 注：data/ 为运行数据（事件/日志），一般无需回滚；如需一并回滚取消下行注释
# cp -a /vol2/1000/AI专用/backups/phase1-baseline-20260804-171425/data /vol2/1000/AI专用/Agent\ OS/iso-sand/
```
> 终极回滚（同时放弃 Phase 1）：`/vol2/1000/AI专用/backups/phase0-baseline-20260804-165012/`（MANIFEST.md 为清单）。

## 七、遗留问题 / 待决策

1. **D2（玄鉴接入）**：仅占位（`xuanjian.pipe` handler no-op + 注册表预留）；玄鉴评分无校准/无消费方，本次不实施，等 dandan 决策。
2. **handler 无重试**：失败单次即死信（旧 rules 有 3 次指数退避）。如需重试可给 HandlerRegistry 加 per-handler `max_retries`（下阶段可做）。
3. **fork 4 条丰碑任务未接入**：属 D5（monument_bridge）范畴；若 dandan 决定由主总线代跑，需先解决"双调度器重复执行"（停 fork 调度器或加分布式锁）。
4. **旧 3 条 rules 休眠**：handler 已接管，rules 保留为兼容回退；迁移期结束可考虑清理 event_rules.yaml。
5. **verify_daemon 监控 cron 来源未定位**（30min 级健康检查重启后未再写入）；同构沙盘 verify_daemon 本体建议暂不恢复（见 §四）。
6. **心跳触发 audit 噪音**：bus_heartbeat 的 task_complete/OK 每 5 分钟触发一次 audit_bridge.log 记录（audit.py 无副作用，仅追加日志）；若嫌噪音可给心跳任务改独立事件类型或调整调度频率。
7. **自测副作用残留**：consumer quick_test 首次运行（修复 enable_handlers 前）向 丰碑 data/alerts.log 写了 1 条测试告警（trace_id=test-004，17:15:18）——仅测试残留，未清理（不碰丰碑文件，遵守红线），如介意可手工删该行。
