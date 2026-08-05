# VERSION.md — iso-sand（Agent OS 主总线）版本存档

> 存档时间：2026-08-04 19:27（Phase 5 定型）
> 当前版本：**v0.7.0**
> 存档方式：本目录为 `cp -a` 完整快照（无 git 仓库，目录级归档）
> 存档位置：`/vol2/1000/AI专用/backups/phase5-archive-iso-sand-20260804-192727/`

---

## 一、版本沿革

| 版本 | Phase | 日期 | 一句话摘要 |
|------|-------|------|-----------|
| v0.4.1 | 基线 | 2026-07-22 前 | 丰碑 fork 前的原始主总线（定时调度器 + 事件消费者 + 写入锁） |
| v0.6.0 | Phase 1 | 2026-08-04 | 安全加固：exec+script 安全分派（shell=False）+ 原子写 + D7 契约三件套（schema_version / event_type 注册表 / event_id 幂等去重 + trace_id 硬规范） |
| v0.7.0 | Phase 2 | 2026-08-04 | handler 注册表（D6）+ 调度器接真实任务（tasks.yaml + 心跳）+ 拓扑工具；D2 玄鉴接入延后（注册表预留） |
| v0.7.0 | Phase 3 | 2026-08-04 | 胶水层接入：`interfaces.store` / `interfaces.recall` handler 宿主化（HTTP 调 glue_server 19000，shell=False） |
| v0.7.0 | Phase 4 | 2026-08-04 | LMS 双向反馈：`lms.feed` handler（LMS 塑形喂入）+ lms.* 事件注册为 active（软参考信号） |
| v0.7.0 | Phase 5 | 2026-08-04 | 定型与治理：本存档 + ARCHITECTURE-FINAL.md + replay_dlq.py + compact_ids.py（见 iso-sand 侧文档） |

版本号载体：`src/__init__.py` 的 `__version__`（当前 "0.7.0"）。Phase 3/4 功能叠加但未升版本号——v0.7.0 覆盖 Phase 2-4 全部功能。

## 二、Phase 变更摘要（各 PHASE*_CHANGELOG.md 详见）

- **Phase 1（v0.4.1→v0.6.0）**：`log_writer.py` 新增 atomic_rewrite/cleanup_stale_tmp（追加仍 append+flock+fsync）；`event_consumer.py` 移植安全分派 `_dispatch_safe()`（EVENT_DATA 环境变量传事件、exec 白名单仅 python/python3、shell=False）+ 幂等去重（内存集合 + data/processed_ids.jsonl）；`task_scheduler.py` 事件升级 v1.1 契约；`deploy/event_rules.yaml` 3 条规则改 exec+script；`deploy/event_schema.yaml` v1.0→v1.1。
- **Phase 2（v0.6.0→v0.7.0）**：新增 `src/handlers.py`（Handler 抽象 + HandlerRegistry + 异常隔离 + 限流；内置 audit.task_complete / alert.anomaly / archive.audit_result / xuanjian.pipe 占位）；consumer 改 handler 链优先、旧 rules 兼容回退；调度器从 tasks.yaml 加载任务（bus_heartbeat 每 5 分钟）；新增 `src/topology.py`（拓扑 + 环检测）。
- **Phase 3**：`handlers.py` 新增 GlueHttpMixin + `interfaces.store` / `interfaces.recall` handler（POST glue_server 127.0.0.1:19000，fail-open，结果写 operation_log）。
- **Phase 4**：`handlers.py` 新增 `lms.feed` handler（订阅 interfaces.store / task_complete / milestone，POST LMS 8190 /feed，限流 1s，fail-open）；event_schema.yaml 中 lms.plastified / lms.self_ref / lms.dream_complete / lms.feed 全部 active。
- **Phase 5**：新增 `src/replay_dlq.py`（死信重放，dry-run/注入双模式）+ `src/compact_ids.py`（processed_ids 按龄压缩）；本 VERSION.md 存档。

## 三、当前运行状态（存档时点）

- scheduler：PID 84905（`python3 .../iso-sand/.run_scheduler.py`，tick 30s，tasks=deploy/tasks.yaml）
- consumer：PID 84910（`python3 .../iso-sand/.run_consumer.py`，poll 3s，handler 链优先）
- 日志：`/tmp/agent_os_scheduler.log`、`/tmp/agent_os_consumer.log`
- 数据：`data/event_bus.jsonl`（941 行）/ `event_bus.seek` / `operation_log.jsonl`（98 行）/ `processed_ids.jsonl`（1083 行）/ `.dead_letter_queue.jsonl`（9 条验证期噪音）
- 关联服务：glue_server 19000（memory-integration-layer，python3）、LMS API 8190 + MCP（living-memory-system-cloud）

## 四、回滚指引

### 场景 A：总线代码/配置回退（最常见）
1. 停机：`bash /vol2/1000/AI专用/Agent OS/iso-sand/stop_all.sh`（或 kill $(cat data/scheduler.pid) $(cat data/consumer.pid)）
2. 用本存档覆盖现场（**注意：会覆盖现场 data/ 与 deploy/，如需保留事件数据先备份现场 data/**）：
   ```bash
   cp -a /vol2/1000/AI专用/backups/phase5-archive-iso-sand-20260804-192727/. \
         /vol2/1000/AI专用/Agent\ OS/iso-sand/
   ```
3. 启动：`bash /vol2/1000/AI专用/Agent OS/iso-sand/start_all.sh`
4. 验证：ps 见 scheduler/consumer 双进程；`python3 src/topology.py` 正常；operation_log 有消费记录

### 场景 B：仅回退某 Phase
- 回退 Phase 1 增量：用 `backups/phase0-baseline-20260804-165012/` 覆盖
- 回退 Phase 2 增量：用 `backups/phase1-baseline-20260804-171425/` 覆盖
- 回退 Phase 4 前的 LMS 侧状态：用 `backups/phase4-lms-pre-20260804-174037/` 覆盖 LMS 相关文件
- 规则：**数据文件（data/event_bus.jsonl 等）默认保留现场**，只回退代码/配置（src/ deploy/ *.sh）；除非明确要回退事件数据本身

### 场景 C：LMS 侧回退
LMS 有独立 git（`living-memory-system-cloud`），回退走 git checkout；未提交改动见该仓 git status（Phase 4 改动未 commit，回退前先备份工作区）。

## 五、注意事项

- 本目录为只读存档基线，**不要**在其中继续开发；开发在 `Agent OS/iso-sand/` 现场进行
- 物理迁移（iso-sand → Agent OS/bus/）当前**暂缓**（详见 ARCHITECTURE-FINAL.md §迁移评估），未来迁移时本存档是回滚锚点
- 存档不含 __pycache__ 之外的大型产物，体积 944K；如需恢复运行态，data/ 内 PID 文件已过期，直接 start_all.sh 即可
