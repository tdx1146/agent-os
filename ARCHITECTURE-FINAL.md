# ARCHITECTURE-FINAL.md — Agent OS 总线工程最终架构（权威文档）

> 版本：v1.0 ｜ 日期：2026-08-04 ｜ 工程：Agent OS 总线改良工程 Phase 5（定型与治理）
> 定位：**以后编程有据可依的标准接口文档** —— 新系统接入、事件开发、排障一律以本文为准。
> 配套：iso-sand/VERSION.md（版本存档）、iso-sand/deploy/event_schema.yaml（事件契约）、iso-sand/PHASE*_CHANGELOG.md（变更史）

---

## 0. 架构总览（ASCII）

```
                        ┌──────────────────────────────────────────────┐
                        │            Agent OS 统一事件总线                │
                        │      /vol2/1000/AI专用/Agent OS/iso-sand/     │
                        │  ┌──────────────┐        ┌─────────────────┐  │
   ┌──────────┐         │  │ task_scheduler│        │  event_consumer  │  │
   │ 各系统    │ 写事件   │  │ (PID 84905)   │        │  (PID 84910)     │  │
   │ 生产者    ├────────►│  │ tick 30s      │ 事件   │  poll 3s         │  │
   │(LMS/胶水/ │  (v1.1) │  └──────┬───────┘ ├──────►│  handler 链优先   │  │
   │ 调度器/   │         │         │ 写      │        │  旧 rules 回退    │  │
   │ 未来系统) │         │  ┌──────▼───────┐ │        └───┬─────────┬───┘  │
   │          │         │  │ data/        │ │            │ 调 handler│    │
   └──────────┘         │  │ event_bus.jsonl◄┘            ▼         ▼    │
                        │  │ (JSONL 哑管道)│        丰碑桥接      HTTP 调   │
                        │  │ seek/oplog/  │        handler     (glue/LMS) │
                        │  │ processed/dlq │        (shell=False)         │
                        │  └──────────────┘                              │
                        └──────────┬─────────────────────────────────────┘
                                   │  POST /store /recall /status  (127.0.0.1:19000)
                        ┌──────────▼───────────────────┐   ┌──────────────────┐
                        │  memory-integration-layer    │   │ living-memory-    │
                        │  glue_server (python3, 19000) │◄──┤ system-cloud      │
                        │  ├─ sandglass_vault (txt 源) │   │ LMS API (8190)    │
                        │  ├─ LMSAdapter (8190)        │   │ MCP (stdio 已注册) │
                        │  └─ VectorAdapter (bge-m3)   │   │ bus_events.py     │
                        └──────────────────────────────┘   │ (发布侧,熔断)     │
                                                           └──────────────────┘
   主 AI（OpenClaw）── MCP(lms-memory/lms-http) ──► LMS；插件(glue-memory-injector, 待注册) ──► glue /recall
```

**核心原则：总线是哑管道。** 总线只负责"按契约运载事件"，不替任何系统做决策；订阅方把事件当软参考信号，可忽略、可降级。

---

## 1. 组件清单（路径 / 端口 / PID 约定）

| 组件 | 路径 | 端口/协议 | PID 约定 | 状态 |
|------|------|-----------|----------|------|
| 主总线（iso-sand） | `/vol2/1000/AI专用/Agent OS/iso-sand/` | 无端口（文件总线） | `data/scheduler.pid`、`data/consumer.pid` | v0.7.0 运行中 |
| 调度器 | `iso-sand/src/task_scheduler.py` | — | 启动脚本写 pid；日志 `/tmp/agent_os_scheduler.log` | PID 84905 |
| 消费者 | `iso-sand/src/event_consumer.py` | — | 启动脚本写 pid；日志 `/tmp/agent_os_consumer.log` | PID 84910 |
| 写入锁中间件 | `iso-sand/src/log_writer.py` | — | — | 追加写 append+flock+fsync；重写 atomic（tmp+fsync+os.replace） |
| handler 注册表 | `iso-sand/src/handlers.py` | — | — | 7 handler（见 §4） |
| 契约 | `iso-sand/deploy/event_schema.yaml` | — | — | v1.1 |
| 规则（legacy） | `iso-sand/deploy/event_rules.yaml` | — | — | 3 条，兼容期标注 |
| 任务 | `iso-sand/deploy/tasks.yaml` | — | — | bus_heartbeat 每 5 分钟 |
| 胶水层 | `/vol2/1000/AI专用/memory-integration-layer/` | HTTP 127.0.0.1:19000 | 无 pid 文件（`--daemon` fork）；日志 stderr | 运行中（system python3，非 .venv） |
| 胶水端点 | — | POST `/recall` `/store` `/status` `/contribute`；GET `/health` | — | /recall 协同检索（文本0.3+向量0.5+LMS激活0.2） |
| LMS | `/vol2/1000/AI专用/living-memory-system-cloud/` | HTTP 127.0.0.1:8190；MCP stdio | MCP 由 openclaw mcp 配置拉起 | 运行中；672 测试 |
| LMS 发布侧 | `living-memory-system-cloud/runtime/bus_events.py` | 直写总线文件 | 熔断器（5 连败→冷却 10 分钟） | LMS_BUS_FILE 可覆盖默认 |
| OpenClaw 记忆注入插件 | `/vol1/@apphome/trim.openclaw/data/home/.openclaw/plugins/glue-memory-injector/` | HTTP 调 glue 19000 /recall | 由 OpenClaw 插件系统加载（待主会话注册） | 代码就绪，未注册 |
| 数据文件 | `iso-sand/data/` | — | — | event_bus.jsonl / event_bus.seek / operation_log.jsonl / processed_ids.jsonl / .dead_letter_queue.jsonl |

**启动约定**：一切以 `iso-sand/start_all.sh` 为准（内部调 start_scheduler.sh + start_consumer.sh）。启动脚本生成 `.run_*.py` runner（内嵌绝对路径）→ nohup python3 → 写 pid 文件。停止用 `stop_all.sh`。

---

## 2. 事件契约 v1.1 速查

### 2.1 事件必填字段（生产者必须带全）

```json
{
  "t": "2026-08-04T19:28:00+08:00",      // ISO8601 含时区（LogWriter 自动补）
  "schema_version": "1.1",               // 强制；老事件缺失容忍默认 1.0
  "event_id": "uuid4",                   // 幂等去重键（推荐必带）
  "event_type": "interfaces.store",      // 必须在 event_schema.yaml 注册表
  "producer": "lms",                     // 模块名
  "result": "OK",                        // 枚举: OK/FAIL/WARN/TIMEOUT
  "trace_id": "phase5-xxx-001"           // 硬规范；缺失 consumer 打 WARN 但继续
}
```

可选：`detail`（描述）、`payload`（自由扩展对象）。

### 2.2 写入方式（只允许两种）

1. **LogWriter**（推荐，自带锁）：`LogWriter(path).write({event_type, producer, result, ...})` —— 线程锁 + fcntl 进程锁 + fsync
2. **LMS bus_events.BusEventPublisher**（LMS 专用）：自动补 t/event_id/trace_id + 熔断 + 静默降级（永不抛异常回主循环）

**禁止**：裸 open().write() 直写总线文件（会与 consumer 原子重写竞争）。

### 2.3 消费语义

- consumer 按 `event_id` 幂等去重（内存集合 ≤10 万 + `data/processed_ids.jsonl` 持久化，重启全量重载）
- handler 链优先：注册了 handler 的事件走 handler 链；未注册的回退旧 rules（互斥不双跑）
- 单个 handler 失败 → 死信（`data/.dead_letter_queue.jsonl`）+ 异常隔离，不拖垮消费循环（fail-open）
- 无 event_id 的老事件不参与去重（向后兼容）

### 2.4 事件注册表（18 项，全量见 deploy/event_schema.yaml）

| event_type | 生产者 | 消费者（handler） | 状态 |
|-----------|--------|------------------|------|
| task_complete | core/task_scheduler | audit.task_complete + lms.feed + rule-task-complete(legacy) | active |
| anomaly | core 多源 | alert.anomaly + rule-anomaly-escalate(legacy) | active |
| audit_result | xuanjian（D2 延后） | archive.audit_result + rule-audit-archive(legacy) | active |
| milestone | core/丰碑 | lms.feed | active |
| consumer_action | core/event_consumer | —（operation_log 自记录） | active |
| interfaces.store | 胶水/总线侧 | interfaces.store + lms.feed | active |
| interfaces.recall | 胶水/总线侧 | interfaces.recall | active |
| lms.plastified / lms.self_ref / lms.dream_complete / lms.feed | lms | lms.feed 是 handler（订阅 store/task_complete/milestone）；lms.* 事件本身无人订阅（软参考信号，预期） | active |
| xuanjian.pipe | xuanjian | xuanjian.pipe（占位 no-op） | active（占位） |
| sandglass.heartbeat / scheduler.tick / scheduler.task_done / ai.decided / ai.action_done / xuanjian.audit_result | 各系统 | — | reserved_phase2（预留） |

---

## 3. 新系统接入三步（handler 注册规范）

> 适用：任何新系统要"消费总线事件做动作"。生产事件只需 §2.2 写入 + 注册 event_type。

**第 1 步：登记事件类型** —— 编辑 `iso-sand/deploy/event_schema.yaml`：
- 在 `event_types` 增加 `<system>.<domain>.<action>` 命名空间条目（status: active 或 reserved）
- 命名规范：`<系统>.<域>.<动作>`（如 `interfaces.store`、`lms.feed`）；核心事件（task_complete 等）保留无前缀
- 描述里写明生产者 + 消费者 + 软参考语义（若适用）

**第 2 步：写 handler** —— 在 `iso-sand/src/handlers.py`：
```python
class MyHandler(Handler):
    handler_name = "my.sys.action"           # 唯一签名 <system>.<domain>.<action>
    event_types = ["my.sys.event"]           # 订阅哪些事件（可多个）
    results = None                            # None=任意 result 都接收；或 ["OK"]

    def handle(self, event):
        # 幂等/副作用动作；失败 raise → registry 记死信（fail-open）
        # 外部调用必须 shell=False（subprocess 数组传参）或 HTTP（urllib）
        return True

    def load(self):
        # 可选：启动探活依赖服务（不可达仅 WARN 不阻断）
        pass
```
- 然后在 `build_default_registry()` 里 `registry.register(MyHandler())`
- 外部依赖地址用环境变量可覆盖（参照 `GLUE_SERVER_URL`、`LMS_URL`），默认值指向本机

**第 3 步：验证**：
```bash
python3 iso-sand/src/topology.py          # 确认 生产者→消费者 拓扑出现你的 handler
# 受控注入一条测试事件（trace_id 带 test 标记）：
python3 -c "from src.log_writer import LogWriter; LogWriter('iso-sand/data/event_bus.jsonl').write({'event_type':'my.sys.event','producer':'my-sys-test','result':'OK','trace_id':'my-sys-e2e-001'})"
tail iso-sand/data/operation_log.jsonl    # 确认 handler 执行
```
- 测试事件记得后续清理（或直接用 `--dry-run` 验证工具）；不留噪音进死信/记忆库

**红线**：
- 禁止 A→B→A 订阅环（长度≥2，topology.py 会 WARN）
- 禁止 shell=True / 命令字符串拼接传事件数据（事件数据只能走 EVENT_DATA 环境变量或参数数组）
- 禁止 handler 阻塞消费循环（限流用 Handler 的 `rate_limit` 字段，≥1s）

---

## 3.5 自我怀疑系统（doubt-system，Phase 6 接入）

- 代码：Agent OS/doubt-system/（GitHub agent-os 仓库）+ 胶水层 doubt_adapter
- 职责：记忆信任度 / 怀疑账本 / 夜巡(23:30) / 反教条复核 —— 「聪明 = 持续自我怀疑」
- 总线：doubt.episode 事件（v1.1）→ lms.feed → LMS /feed 塑形（自我怀疑喂潜意识）
- cron：`30 23 * * *` night_patrol_run.sh（每日幂等 marker）
- 文档：DOUBT-SYSTEM.md

## 4. 物理迁移评估（Phase 5 结论：**暂缓**）

### 4.1 现状盘点
- iso-sand：**无 git**（已 cp -a 存档：`backups/phase5-archive-iso-sand-20260804-192727/`）
- memory-integration-layer：有 git（master，dirty：glue_server.py + vector_adapter.py 未提交 + PHASE3_CHANGELOG 未跟踪）
- living-memory-system-cloud：有 git（master，dirty：api/server.py + runtime/loop.py 未提交 + bus_events.py 等未跟踪）
- **均不 commit / 不 push**（由主会话决定提交策略）

### 4.2 方案第六节目标结构 vs 现状
目标：`Agent OS/bus/`（原 iso-sand）+ `Agent OS/adapters/`（各系统 adapter）+ `Agent OS/interfaces/`（胶水层）+ 分工仓 + 版本标签。

### 4.3 受影响的路径引用清单（grep 实测）
若 iso-sand 物理移动到 `Agent OS/bus/`，以下全部要改：

| # | 位置 | 引用数 | 说明 |
|---|------|--------|------|
| 1 | `iso-sand/start_scheduler.sh`（runner 模板） | 5 处 | sys.path + event_file + operation_log + tasks_file |
| 2 | `iso-sand/start_consumer.sh`（runner 模板） | 6 处 | sys.path + 4 数据文件 + rules_file |
| 3 | `iso-sand/.run_scheduler.py` / `.run_consumer.py` | 11 处 | 运行中进程 84905/84910 正在执行这两个文件，内嵌旧绝对路径 |
| 4 | `living-memory-system-cloud/runtime/bus_events.py` | 1 处 | `_DEFAULT_BUS_FILE` 硬编码旧路径 |
| 5 | `所有自动化/找回自己/scripts/handlers/event_bus_handler.py` | 2 处 | 读 operation_log + seek |
| 6 | `所有自动化/找回自己/scripts/handlers/status_handler.py` | 1 处 | 读 scheduler.pid |
| 7 | `丰碑网络/code/event_bus/start_*.sh`（fork 副本） | 11 处 | 冻结 fork，实际已由 iso-sand 替代（可弃用） |
| 8 | edit-web-github v5.1 内 handlers 副本 | 3 处 | 历史版本副本（可不动） |
| 9 | 全局设计/认知快照等 md 文档 | ~6 处 | 文档引用 |

合计 ≥40 处代码/配置引用 + 运行中进程 2 个需要停机窗口。

### 4.4 结论与理由
**暂缓物理迁移。** 理由：
1. **零功能收益**：bus/adapters/interfaces 目录重组是纯整理；事件契约、handler 机制、路径约定已在本文件与 VERSION.md 落档，逻辑边界已清晰，物理位置不影响编程有据可依
2. **高改动面**：≥40 处引用 + 2 个运行中进程（PID 84905/84910 内嵌绝对路径，迁移必须停机重启）
3. **多系统耦合**：LMS（bus_events 默认路径）、找回自己（读日志/pid）、胶水层均依赖现状；迁移需跨仓同步改
4. **风险不对称**：迁移出错会影响正在运行的记忆反馈链路（Phase 4 刚打通），收益仅为目录美观

### 4.5 未来迁移 checklist（条件成熟时执行）
- [ ] 停机窗口：`stop_all.sh`，确认 84905/84910 退出（kill -0 检查）
- [ ] `mkdir -p Agent OS/bus`，`git mv`/`mv iso-sand/* Agent OS/bus/`（保留 data/）
- [ ] 建过渡符号链接 `ln -s bus iso-sand`（或一次性改全部引用，见 4.3 清单 1-8）
- [ ] 改 `runtime/bus_events.py` 的 `_DEFAULT_BUS_FILE`；同步改 找回自己 3 处
- [ ] 弃用/删除 `丰碑网络/code/event_bus/` fork 副本（先确认无人引用）
- [ ] `start_all.sh` 重启 → `topology.py` 无异常 → operation_log 有消费 → DLQ 无新增
- [ ] 更新本文件路径表 + VERSION.md；重新 cp -a 存档
- [ ] 若启用 git：以 bus/ 为独立仓，打 `v0.7.0` 标签，LMS/胶水各自仓打标

---

## 5. Schema 演进规则（事件契约变更流程）

1. **兼容优先**：新字段一律 optional；旧字段不删除只废弃（consumer 容忍缺失并默认值）
2. **版本号语义**：破坏性变更（删字段/改语义）→ `schema_version` 升 1.x；追加性变更 → 保持版本号，只更新 event_schema.yaml
3. **注册表先行**：任何新 event_type 必须先进 `deploy/event_schema.yaml` 才能上线（topology.py 一致性检查兜底）
4. **双向兼容**：v1.0 老事件可被 v1.1 consumer 消费；v1.1 新事件不破坏老消费者（老消费者忽略未知字段）
5. **变更记录**：每次契约变更在对应 PHASE*_CHANGELOG.md 记一行（版本号 + 日期 + 变更点）
6. **幂等约定不变**：event_id 是去重唯一键，重放/重投必须保留原 event_id（见 replay_dlq.py 设计）

---

## 6. 治理工具（Phase 5 新增）

| 工具 | 路径 | 用法 |
|------|------|------|
| 拓扑报告 | `src/topology.py` | `python3 src/topology.py [--json]`；环检测 + 孤儿事件检查 |
| 死信重放 | `src/replay_dlq.py` | `--dry-run` 列出；默认重新注入总线（保留原 event_id，consumer 幂等去重）；详见 `Agent OS/事件拓扑-20260804.md` |
| ids 压缩 | `src/compact_ids.py` | `python3 src/compact_ids.py [--age-days N]`（默认 7）；压缩 processed_ids.jsonl |
| 版本存档 | `backups/phase5-archive-iso-sand-*/` | VERSION.md 见 §回滚指引 |

---

*本文档与 iso-sand/VERSION.md、deploy/event_schema.yaml 共同构成 Agent OS 总线工程的"标准接口文档集"。*
