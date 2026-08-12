# self_pulse 套件（生产 v3，随 agent-os 分发）

> 2026-08-13 入库（复现缺口清单 #9 更正：self_pulse 生产 v3 不在任何 GitHub main 仓 ——
> edit-web.py 仓 main 与 GitHub 分叉 20 commit（待 dandan 合并决策，缺口 #3/#7），
> qingruan-scripts 仓为旧版。本目录是**唯一可从 GitHub 拿到的生产 v3 发行版**。）

## 内容（8 件）

| 文件 | 作用 |
|------|------|
| `pulse-cron.sh` | cron `*/10` 入口：导出环境 → 调 self_pulse_cli.py → 更新 /tmp/pulse-status.json |
| `self_pulse_cli.py` | 自主脉冲 CLI（v2.5 唤醒策略：惊讶度 z-score 突变才是唤醒信号；白天禁醒/夜间可醒） |
| `salience_gate.py` | 显著性判据（Baldi & Itti；novelty×salience×goal 三路 + 梦惊讶度第4通道 SG_DREAM_FEED + 怀疑第5通道 SG_DOUBT_FEED） |
| `sleep_pressure.py` | 体力系统（Borbély Process S 负反馈，防自激；休眠强制期 + anomaly 强唤醒） |
| `wake_client.py` | 唤醒客户端：A 通道 POST /hooks/wake（旧）+ B 通道 chat.send 注入[梦醒]（WAKE_CHANNEL=b） |
| `session-reset-watchdog.py` | 会话重置看门狗（cron `*/2`）：检测 *.jsonl.reset.* 归档 → 恢复为可浏览 |
| `test_awaken.py` | 唤醒链端到端测试 |
| `SELF_PULSE_README.md` | 原模块文档（轻如烟 scripts 同步） |

## 与生产版差异（仅可移植性，行为等价）

生产运行实例在 `LIGHT_HOME/scripts/`（= edit-web.py 仓本地 main）。本目录拷贝做了 4 处
**机器路径去硬编码**（生产版不改，避免动运行中实例）：

1. `wake_client.py`：默认 openclaw.json 定位改为 `OPENCLAW_HOME > HOME > ~` 动态解析
   （原默认 `/vol1/@apphome/...` 是 dandan 机器路径）
2. `pulse-cron.sh`：`OPENCLAW_HOME` 兜底改 `$HOME/.openclaw`（env.local 定义则优先）
3. `session-reset-watchdog.py`：sessions 目录兜底改 `~/.openclaw/agents/main/sessions`
   （正式部署经 env.local `RESET_WATCHDOG_SESSIONS_DIR` 配置）
4. `self_pulse_cli.py`：`_SELF`（待办源 backlog.md）改 `WORKSPACE_HOME` env 驱动；
   `_BUS_FILE` 默认改 `$AGENT_OS_HOME/iso-sand/data/event_bus.jsonl`
5. `sleep_pressure.py`：sessions 目录兜底同 #3（`SP_SESSION_DIR` env 可覆盖）

## 部署（全新机器）

edit-web.py 仓经 bootstrap clone 到 `$EDITOR_HOME`（= `$LIGHT_HOME/scripts`）后，
本套件即随仓到位（edit-web.py 本地 main 已含这些文件）。**若 edit-web.py GitHub main
尚未合并（缺口 #3），用本目录覆盖**：

```bash
# 方式 A（推荐）：等缺口 #3 合并后随 edit-web.py 仓分发，无需手动
# 方式 B（现状）：bootstrap 后手动补齐
cp agent-os/self_pulse/pulse-cron.sh agent-os/self_pulse/*.py "$EDITOR_HOME/"
```

cron（由 `deploy.sh cron-show` 输出，已展开）：
```
*/10 * * * *  bash $LIGHT_HOME/scripts/pulse-cron.sh
*/2 * * * *   python3 $LIGHT_HOME/scripts/session-reset-watchdog.py
```

## 同步纪律

- **生产是权威**：改行为先改 `LIGHT_HOME/scripts/` 生产版（commit 到 edit-web.py 本地 main），
  再同步本目录（机器路径按上述 5 条去硬编码）。
- 缺口 #3（edit-web.py 分叉）合并后，重估是否仍需要本目录（建议保留为发行版锚点，
  文档指向唯一来源，避免 qingruan-scripts 式双份漂移）。
