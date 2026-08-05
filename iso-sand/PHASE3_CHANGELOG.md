# PHASE3_CHANGELOG — 总线 handler 宿主化（胶水层接入）

> 日期：2026-08-04（Phase 3）
> 工程：Agent OS 总线改良工程 Phase 3 —— D4（glue_server 通电）+ D6 深化（胶水 store/recall 作 hexagon handler 宿主，shell 降级为一种 handler）
> 本文件覆盖：`iso-sand`（主总线 v0.7.0）；胶水层侧改动见 `memory-integration-layer/PHASE3_CHANGELOG.md`

---

## 一、改动清单

### 1. `src/handlers.py` — 新增 2 个胶水 handler（HTTP 调 glue_server，shell=False）

**`GlueHttpMixin`**：胶水层 HTTP 调用工具（urllib 标准库，零额外依赖）：
- `post(path, body, timeout)` → POST glue_server（默认 `http://127.0.0.1:19000`，可用 `GLUE_SERVER_URL` 环境变量覆盖）
- `health(timeout)` → GET /health，不可达返回 None（fail-open）

**`InterfacesStoreHandler`**（`interfaces.store`）：
- event_types=`["interfaces.store"]`，results=None（命令通道，任意 result 都接收）
- payload.text / payload.source → POST glue_server `/store`（缺 text 视为非法事件 → 死信）
- 成功后写 operation_log 详情（id/vector/entropy/surprise）
- 调 glue 失败 raise → registry 异常隔离记死信，不拖垮消费循环（fail-open）

**`InterfacesRecallHandler`**（`interfaces.recall`）：
- event_types=`["interfaces.recall"]`，results=None
- payload.query / payload.k → POST glue_server `/recall`（缺 query 视为非法 → 死信）
- **结果写回 operation_log**（count + top N 条 origin/scores/text 摘要，供审计回读）

**生命周期**：两个 handler 均实现 `load()`（启动时探活 glue_server，不可达仅 WARN 不阻断）/ `unload()`（默认空）。

**注册**：`build_default_registry()` 追加注册（注册表现共 6 个 handler：3 个丰碑桥接 + 玄鉴占位 + 胶水 store/recall）。

### 2. `deploy/event_schema.yaml` — 注册表升级（预留 → 已启用）
- `interfaces.store`：`reserved_phase2` → `active`（描述更新为 Phase 3 已启用）
- `interfaces.recall`：`reserved_phase2` → `active`（同上）
- schema_version 保持 **1.1**（纯注册表状态变更，事件字段契约零变化 → 向后兼容）

### 3. 服务重启
- 消费者（`.run_consumer.py`）重启加载新 handler 注册表；调度器（`.run_scheduler.py`）无需改
- 当前运行：scheduler PID `72951` / consumer PID `73136` / glue_server PID `72720`

---

## 二、验证（逐项实测）

### 1. 端到端：`interfaces.store` 总线事件 → glue store ✅
注入 v1.1 事件（schema_version/event_id/trace_id + payload.text="Phase3 总线到胶水 handler 端到端 store 测试", source="bus-e2e"）：
- sandglass.txt 实际追加：`2026-08-04 17:28:10 | bus-e2e | Phase3 总线到胶水 handler 端到端 store 测试`
- operation_log：
  - `interfaces.store | OK | 胶水层 store 成功: id=30eac3d1... vector=True entropy=5.28 surprise=0.097`
  - `event_consumer | OK | handler 链执行成功: interfaces.store/OK (handled=1, failed=0)`
- 死信：0

### 2. 端到端：`interfaces.recall` 总线事件 → glue recall → 回读 ✅
注入 v1.1 事件（payload.query="胶水层通电", k=3）：
- operation_log：`interfaces.recall | OK | 胶水层 recall 成功: query='胶水层通电' count=3 top=[{...text:"Phase3 胶水层通电测试", scores:{total:0.921, lms_activation:1.0}...}]`
- handler 链 OK 记录同步落盘

### 3. 拓扑无环 + 注册表含 interfaces.* ✅
`python3 src/topology.py`：
- `interfaces.store` / `interfaces.recall` 均在拓扑中，消费者为对应 handler
- `✅ 无环（无长度≥2 的订阅环）`；interfaces→interfaces 自环为 INFO（同类于 xuanjian.pipe 自观察，非有害环）
- 既有 WARN（consumer_action/milestone 孤儿事件）为 Phase 2 遗留，非本次引入

### 4. Dummy 降级 fail-open 实测 ✅（详见胶水层 changelog 第二节）
- 停 glue → 注入 store 事件 → 死信 2 条（handler 级 + 链级总账），消费者存活，总线不崩
- 起 glue → 注入 → 恢复 OK，死信不再增长

### 5. 重启 iso-sand 服务确认不影响 ✅
- 完整重启 scheduler + consumer（新 PID），重新注入 store 事件 → 处理正常（sandglass 追加 + operation_log OK）
- 调度器存活证明：`sandglass.heartbeat` 心跳事件持续产生（累计 6 条）
- handler 注册表在重启后正确加载 6 个 handler

---

## 三、handler 接入模式（Phase 5 参考）

新子系统接入 = 在 `handlers.py` 定义 `Handler` 子类（name=`<system>.<domain>.<action>`，event_types 订阅，handle() 返回 bool）+ `build_default_registry()` 注册一行。
不再改 event_rules.yaml + 重启（旧 3 条 rules 保留为兼容回退，仅对无 handler 的 event_type 生效）。

---

## 四、遗留问题 / 观察项

1. **轮询延迟**：消费者 3s 轮询，事件→handler 执行 ≤3s 延迟（与 Phase 2 相同，已知特性）。
2. **interfaces.* 自环标注**：拓扑工具按 handler 名前缀判 producer，interfaces 命名空间自环属"系统内自观察"（命令通道语义：interfaces 既是生产者语义命名空间又是消费 handler 前缀），INFO 级，非设计违规。
3. **死信增长**：fail-open 测试在 `.dead_letter_queue.jsonl` 留了 2 条记录（可作审计样本保留）。
4. **glue_server 依赖运行**：总线 handler 依赖 glue_server 存活；glue 停机时记忆类事件全部进死信（fail-open 但不丢事件原文，可追溯重放）。是否要做死信重放机制，建议 Phase 5 评估。
5. **操作日志膨胀**：interfaces.recall 结果摘要写入 operation_log，长 query 大 k 时会写较长 JSON 行；当前 k≤100 可接受，如高频调用需考虑截断策略。

---

## 五、安全红线遵守

- ✅ 只改 iso-sand（handlers.py / event_schema.yaml / data/*.pid）；未碰丰碑/玄鉴/LMS 核心代码
- ✅ 未做 git 操作；未打印 token/密钥
- ✅ 总线事件只追加注入测试事件（v1.1 契约完整）；测试文本已从沙漏清理（见胶水层 changelog）
- ✅ 服务均以 setsid 启动，防会话清理
