# xuanjian/ — 玄鉴守护进程体系（已并入 agent-os）

> 2026-08-12 玄鉴并入 agent-os 统一维护（dandan：「代码不能散沙」）。
> 本目录是玄鉴的**唯一代码家**，随 `tdx1146/agent-os` 仓分发（复现缺口清单 #2 修正）。

## 来源与并入方式

- **源**：`/vol2/1000/AI专用/AgentOS-IsoSand/同构沙盘/`（本地 git 仓，无 remote）
- **方式**：新目录从零跟踪（不合并历史）。源仓历史保留在本地：关键 commit
  `f61c39e`（玄鉴守护进程 v0.1）、`f12c79e`（履约报告模板+信誉联动）、
  `78452ea`（push_verify ahead 双向计数修复）。源码以源仓工作树为真（2026-08-12）。
- **运行时**：本机运行中的守护进程实例仍在源仓路径（`data/` 不随仓分发）；
  迁移到本目录运行属可选后续（停旧起新，见 SYSTEM.md 组件表备注）。

## 内容

| 路径 | 说明 |
|------|------|
| `src/verify_daemon.py` | 玄鉴守护进程：5min 巡检 operation_log 关键词校验 + PURPOSE 完整性 + 三仓推送真实性验证 |
| `src/ci_verify.py` | 项目级 CI 验证（测试/签名/动态导出） |
| `src/essence_distiller.py` | 轮感结晶（操作日志模式提取） |
| `src/facts_manager.py` | 断言图管理（facts.dict.md，原子写入+自动 commit） |
| `src/iso_logger.py` | 操作日志落盘 |
| `src/verify_claim.py` | 断言核验 + git pre-commit hook + 信誉积分 |
| `tests/` | 单元测试（test_ci_verify.py） |
| `deploy/` | install.sh 一键设置、cron_tasks.json 任务模板 |
| `config/subagent_registry.json` | 监控/蒸馏/验证子代理注册表 |

## 用法

```bash
cd <agent-os>/xuanjian
python3 src/verify_daemon.py &      # 首次运行自动创建 data/（pid/seek/audit）
```

由 agent-os 统一运维入口管理：`stack_ctl.sh`（服务清单 verify 行）、
`deploy.sh` / `status_all.sh`（VERIFY_HOME 优先指向本目录，旧同构沙盘路径回退）。

## 数据边界（重要）

- **`data/` 不随仓分发**（.gitignore）：daemon.pid / daemon.seek / daemon_audit.log /
  operation_log.jsonl / 信誉积分 / 模型文件 均为运行时产物，新机器从空开始。
- 玄鉴审计的事实字典 `facts.dict.md` 由 `facts_manager.py` 维护，属运行数据。

## 环境变量（路径不硬编码；默认值向后兼容本机）

| 变量 | 默认 | 用途 |
|------|------|------|
| `XJ_KERNEL_SPEC_DIR` | `/vol2/1000/AI专用/AgentOS-IsoSand/内核层规范` | PURPOSE.md + snapshots 完整性检查对象 |
| `XJ_DOUBT_HOOK` | `<agent-os>/doubt-system/doubt_hook.py`（旧路径默认） | 连续 FAIL → 怀疑钩子 |
| `XJ_REPO_LMS` | `/vol2/1000/AI专用/living-memory-system-cloud` | push_verify 三仓之一 |
| `XJ_REPO_GLUE` | `/vol2/1000/AI专用/memory-integration-layer` | push_verify 三仓之一 |
| `XJ_REPO_AGENTOS` | `/vol2/1000/AI专用/Agent OS` | push_verify 三仓之一 |

> 已知限制：`内核层规范`（PURPOSE.md/snapshots）本身不在任何 GitHub 仓，
> 复现时需自备或置空（守护进程对缺失路径按 FAIL+快照恢复流程处理，不崩溃）。
