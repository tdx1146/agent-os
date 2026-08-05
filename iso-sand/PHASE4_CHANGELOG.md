# PHASE4_CHANGELOG.md — 总线侧 LMS 双向反馈接入（Phase 4 / D0）

> 日期：2026-08-04 ｜ 工程：Agent OS 总线改良 Phase 4：LMS 双向反馈中枢（D0）
> 总线仍是**哑管道**：运载 lms.* 事件但不替任何系统做决策；订阅方软参考、可忽略。

---

## 1. 新增 handler：`lms.feed`（`src/handlers.py`）

- 签名：`lms.feed`（命名空间规范 `<system>.<domain>.<action>`）
- 订阅事件：`interfaces.store`（记忆写入）、`task_complete`（任务完成）、`milestone`（里程碑）
  —— **不订阅心跳**（噪音）
- 行为：提取事件文本摘要（payload.text → payload.detail → detail → 兜底 type/producer，
  截断 2000 字）→ POST `http://127.0.0.1:8190/feed`（`LMS_URL` 可覆盖，urllib，shell=False）
- 失败 fail-open：调 LMS 失败 raise → registry 异常隔离记死信，不拖垮消费循环
- `load()` 探活：LMS /health 不可达仅警告（handler 已注册，后续 fail-open）
- 限流：`rate_limit=1.0s`（≥1s 间隔，防总线风暴）
- 结果写 operation_log（turn_count/entropy/surprise/text_len，可审计）

## 2. 契约注册表（`deploy/event_schema.yaml`，保持 v1.1）

将原 `reserved_phase4` 的 3 个 lms.* 事件升级为 `active` 并注明软参考语义，新增 `lms.feed`：

| event_type | status | 说明 |
|-----------|--------|------|
| `lms.plastified` | active | LMS 塑形倾向/状态反哺（数值摘要，软参考信号，订阅方可忽略；生产者=LMS） |
| `lms.self_ref` | active | LMS 自我认知透视（蒸馏后限量发布，最高敏感度，默认关闭；软参考信号） |
| `lms.dream_complete` | active | LMS 做梦完成通知（可观测性信号；软参考） |
| `lms.feed` | active | LMS 塑形喂入动作（消费者=总线 handler lms.feed；只喂不指挥） |

## 3. 验证记录

| # | 项 | 结果 |
|---|----|------|
| 1 | handlers.py / log_writer.py 快速自测 | ✅ 全部通过 |
| 2 | 拓扑 | ✅ `python3 src/topology.py`：schema_version=1.1、18 事件注册、7 handler、`cycles: []` 无环；lms.feed 订阅 interfaces.store/task_complete/milestone |
| 3 | 收侧 E2E | ✅ milestone/interfaces.store v1.1 事件 → lms.feed → LMS /feed（operation_log "LMS 塑形喂入成功: turn_count=11"）；interfaces.store 双 handler 链（glue /store + lms.feed）均正常 |
| 4 | 发侧消费 | ✅ lms.plastified/dream_complete（LMS 发布）→ consumer "无匹配规则" 正常跳过，零死信 |
| 5 | 异常隔离 | ✅ LMS /feed 429（限流窗口内）→ lms.feed 记死信，interfaces.store 链继续执行成功，消费循环不中断 |
| 6 | 稳定性 | ✅ sandglass.heartbeat 每 5 分钟持续；consumer 日志 0 ERROR/Traceback |
| 7 | 服务重启 | ✅ stop_all.sh + start_all.sh 重启后 7 handler 加载、lms.feed load() 探活 LMS 健康、心跳恢复、收侧 E2E 通过 |

## 4. 遗留问题 / 已知行为

1. **lms.feed 在 topology 中显示 "active 但无人消费" WARN**：`lms.feed` 是消费者动作记录型
   事件（类比 consumer_action），注册为 active 仅作目录登记；该 WARN 为信息性，非缺陷。
   同理 lms.plastified/self_ref/dream_complete 为"active 但暂无人订阅"——符合
   "软参考信号，订阅方可忽略"设计，沙漏/玄鉴等软参考消费者属后续阶段。
2. **429 限流是双保险**：LMS /feed 侧 10 次/分钟 + handler 侧 1s 间隔；总线繁忙时
   lms.feed fail-open 进死信（可观测、可恢复），不重试不阻塞。
3. 未 git commit/push；未打印 token/密钥。
