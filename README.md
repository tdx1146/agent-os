# Agent OS

> Agent OS 是毛毛（轻如烟）自主系统的**中枢**：事件总线、调度、怀疑系统、运维入口。
> 本仓库也是**系统权威拓扑（TOPOLOGY.md）的宿主**——所有模块的地图都在这。

## 快速入口

- **系统全图（先看这个）**：👉 [`TOPOLOGY.md`](./TOPOLOGY.md) — 8 个模块的位置/端口/仓库/契约，单一事实源
- 一键运维：`bash stack_ctl.sh status|doctor|start`（配置中心 `env.local`）
- 服务状态：`bash status_all.sh`（6 服务进程/端口/健康）
- 事件总线：`iso-sand/data/event_bus.jsonl`（v1.1 契约，schema 见 `iso-sand/deploy/event_schema.yaml`）
- 怀疑系统：`doubt-system/`（详见 `DOUBT-SYSTEM.md`）
- 部署指南：`DEPLOY-GLOBAL.md` / `DEPLOYMENT.md`

## 子模块

| 目录 | 职责 |
|------|------|
| `iso-sand/` | 事件总线（scheduler/consumer）、operation_log |
| `doubt-system/` | 持续自我怀疑（夜巡/反教条/doubt_hook） |
| `docker/` | 容器化编排（5 服务） |
| `kernel/` | 内核层规范（预留） |
| `docs/` | 设计文档（自主唤醒调研/诊断等） |
| `TOPOLOGY.md` | **权威拓扑（本仓库的核心文档）** |
