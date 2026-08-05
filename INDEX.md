# Agent OS — 部署目录

> 部署时间：2026-07-22 16:20
> 源：从姐姐同步的事件总线 v0.4.1 + AgentOS-IsoSand 同构沙盘

---

## 目录结构

```
/vol2/1000/AI专用/Agent OS/
├── iso-sand/                      ← 事件总线系统（独立 sandbox）
│   ├── src/                       ← 源代码
│   │   ├── __init__.py            ←  模块导出
│   │   ├── task_scheduler.py      ←  定时调度器（30s tick）
│   │   ├── event_consumer.py      ←  事件消费者（3s poll）
│   │   └── log_writer.py          ←  写入锁中间件
│   ├── deploy/                    ← 部署配置
│   │   ├── event_rules.yaml       ←  3条消费规则
│   │   └── event_schema.yaml      ←  事件数据契约
│   ├── data/                      ← 运行时数据
│   │   ├── event_bus.jsonl        ←  事件总线文件
│   │   ├── event_bus.seek         ←  消费者偏移
│   │   ├── operation_log.jsonl    ←  操作日志
│   │   ├── .dead_letter_queue.jsonl ← 死信队列
│   │   ├── scheduler.pid         ←  调度器 PID
│   │   └── consumer.pid          ←  消费者 PID
│   ├── start_all.sh               ←  一键启动
│   ├── stop_all.sh                ←  一键停止
│   ├── start_scheduler.sh         ←  启动调度器
│   ├── start_consumer.sh          ←  启动消费者
│   ├── .run_scheduler.py          ←  调度器运行器（自动生成）
│   └── .run_consumer.py           ←  消费者运行器（自动生成）
├── kernel/                        ← 内核层规范（预留）
│   └── ...
```

---

## 守护进程

| 守护进程 | 路径 | PID | 状态 |
|----------|------|-----|------|
| 事件总线调度器 | `iso-sand/start_scheduler.sh` | 1641741 | ✅ 运行中 |
| 事件总线消费者 | `iso-sand/start_consumer.sh` | 1641746 | ✅ 运行中 |
| 玄鉴守护进程 | `AgentOS-IsoSand/同构沙盘/` | 132402 | ✅ 运行中 |

---

## 事件生命周期

```
调度器 (task_scheduler.py)
  │ 定时任务完成后写事件
  ▼
event_bus.jsonl ← 独立事件总线文件
  │
  ▼
event_consumer.py（独立守护线程，3s轮询，readline + tell）
  │ 匹配 event_rules.yaml → 异步分派下游
  │ 限流 + 重试（指数退避3次）+ 死信保护
  ▼
下游动作（bridge/archive/escalate）
  │ 当前已注册：
  │  - rule-task-complete → audit.py（丰碑审计）
  │  - rule-anomaly-escalate → alerts.log（告警）
  │  - rule-audit-archive → archive.py（归档，待完善）
```

---

## 丰碑集成

丰碑网络已集成事件总线：
- `丰碑网络/code/event_bus/` ← 事件总线源码副本
- `丰碑网络/code/core/audit.py` ← 审计桥接（消费者调用）
- `丰碑网络/code/core/archive.py` ← 归档桥接（消费者调用）
- `丰碑网络/code/data/` ← 共享运行数据
- `丰碑网络/data/` ← 告警日志

---

## 启动/停止

```bash
# 启动全部
bash /vol2/1000/AI专用/Agent\ OS/iso-sand/start_all.sh

# 停止全部
bash /vol2/1000/AI专用/Agent\ OS/iso-sand/stop_all.sh
```
