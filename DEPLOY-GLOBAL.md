# DEPLOY-GLOBAL.md — 全局部署统一化手册（2026-08-10）

> 目的：让「轻如烟体系」在任何一台机器上都能**拷贝即部署**，部署者不需要
> 记忆每个服务的启动命令，也不需要逐行改脚本里的路径。
>
> 核心思想：**配置集中 + 零硬编码 + 一键校验**。
> 所有绝对路径只允许出现在一个文件：`env.local`（配置中心）。脚本要么读它，
> 要么用「相对路径推导」兜底，绝不写死绝对路径。

---

## 1. 体系全景（6 个常驻服务 + 编辑器）

| 服务 | 端口 | 目录变量 | 启动入口 |
|---|---|---|---|
| 沙漏 HTTP API | 17333 | `SANDGLASS_SOURCE` | `python3 sandglass_http_api.py`（P0-1/2/3 补丁，fork `tdx1146/nyx`） |
| 活体记忆 LMS API | 8190 | `LMS_HOME` | `.venv/bin/python -m api.run`（体验层 A-D：/react/解读段/过滤/元目的翻转/置信度场） |
| 胶水层 glue_server | 19000 | `GLUE_HOME` | `python3 glue_server.py`（含 /react 薄代理） |
| 总线调度器 scheduler | — | `ISO_SAND_HOME` | `bash start_scheduler.sh` |
| 总线消费者 consumer | — | `ISO_SAND_HOME` | `bash start_consumer.sh`（订阅 sandglass.entry，LMS_FEED_RETRIES 逃生门） |
| 玄鉴 verify_daemon | — | `VERIFY_HOME` | `python3 src/verify_daemon.py` |
| 编辑器 edit-web | 18888 | `EDITOR_HOME` | `python3 edit-web.py`（轻如烟自愈脚本托管） |

统一入口：**`./stack_ctl.sh`**（一个命令管全部，无需记忆各服务启动代码）。

---

## 2. 新机器部署步骤（5 步）

```bash
# ① 拷贝仓库（保持目录间相对布局，或任意布局均可——路径由 env.local 决定）
#    需要：Agent OS / 所有自动化/轻如烟 / living-memory-system-cloud /
#          memory-integration-layer / AgentOS-IsoSand/同构沙盘
cd <你的>/Agent\ OS

# ② 生成本机配置（从模板拷贝）
./stack_ctl.sh setup
#    → 自动 cp env.template env.local，并给出路径校验结果
#    → 若报缺目录：编辑 env.local 的【A. 机器根变量】一节，改成你机器上的真实路径

# ③ 全配置体检（路径存在 / 端口 / 依赖命令，全绿即就绪）
./stack_ctl.sh doctor

# ④ 一键启动全部服务（幂等：已在跑的服务自动跳过）
./stack_ctl.sh start

# ⑤ 确认 6 服务全绿
./stack_ctl.sh status
```

> 换机器只需改 `env.local` 的「A. 机器根变量」约 8 个路径 + 端口节，
> 其余变量（`SANDGLASS_SOURCE`/`RUN_DIR`/`LOG_DIR`/`LMS_URL`…）全部自动派生。

### 2.5 体验层部署（2026-08-11，新代码生效要点）

> 体验层 A-D（/react 实时反应+解读段、子代理过滤、元目的翻转、怀疑融入置信度场）代码已在三仓 main，**部署后必须重启才生效**（不重启=静默跑旧版，见 SYSTEM.md §5 坑 16）。

```bash
# ① 重启 LMS（必须先 source .env，否则静默降级）
cd "$LMS_HOME" && set -a; . ./.env; set +a && .venv/bin/python -m api.run --host 127.0.0.1 --port 8190 &
# ② 重启 glue（/react 薄代理）
cd "$GLUE_HOME" && python3 glue_server.py --host 127.0.0.1 --port 19000 &
# ③ 重启 consumer（订阅 sandglass.entry + LMS_FEED_RETRIES）
cd "$ISO_SAND_HOME" && bash start_consumer.sh
# ④ 重载 OpenClaw 插件（memory-recall.js 三路并行；不重载=旧两路）
#    gateway 插件重载按 OpenClaw 部署流程处理
# ⑤ 验证（详见 SYSTEM.md §3.5 部署后 10 分钟验证清单）
curl -s -X POST http://127.0.0.1:8190/react -H 'Content-Type: application/json' -d '{"user_input":"契约校验探针","k":0}' | head -c 300
```

**新增/生效环境变量（体验层 & 2026-08-11 修复）**：`WAKE_CHANNEL`（self_pulse 唤醒出口 a/b）、`SG_DREAM_FEED`/`SG_DOUBT_FEED`（salience_gate 第 4/5 通道，默认关）、`LMS_FEED_RETRIES`/`LMS_FEED_TIMEOUT`（consumer 重试逃生门）、`LMS_FEED_RATE_LIMIT`（LMS /feed 限流）、`LMS_CLOUD_EMBED_FALLBACK_URL`（embed 备用端点）、`SANDGLASS_DEDUP_WINDOW`/`SANDGLASS_SENDER_MAP`/`SANDGLASS_MAX_TEXT_LEN`/`SANDGLASS_BUS_FILE`/`SANDGLASS_BUS_MIN_INTERVAL`（沙漏 P0-1/2/3）。全部含义见 `SYSTEM.md §3.1` 核心环境变量表。

### 常用运维命令

```bash
./stack_ctl.sh status              # 全部服务状态一览
./stack_ctl.sh health              # 深度健康检查（HTTP 层逐个探测）
./stack_ctl.sh restart lms-api     # 重启单个服务
./stack_ctl.sh stop                # 按依赖逆序优雅停止全部
./stack_ctl.sh logs glue           # 跟随某服务日志
./stack_ctl.sh list                # 服务清单
```

### 兼容旧入口（行为不变）

- `bash start_all.sh` / `status_all.sh` / `stop_all.sh` —— 同样读 env.local，保留可用
- `iso-sand/start_all.sh` —— 调度器+消费者独立入口
- `scripts/lms_ctl.sh`（LMS 仓库）—— 自动发现 Agent OS/env.local，找不到则用自身默认
- 轻如烟 `health-check.sh` / `health-loop.sh` / `pulse-cron.sh` / `watchdog.sh` /
  `start-clean.sh` / `start-health-loop.sh` —— 全部读同一配置，缺失时按脚本位置推导
- `session-reset-watchdog.py` —— 读 env.local 的 `RESET_WATCHDOG_*` 变量

---

## 3. 配置中心说明（env.local）

文件：`Agent OS/env.local`（模板：`Agent OS/env.template`，已 gitignore，绝不入库）。

```
A. 机器根变量    —— 新机器唯一需要改写的部分（8 个路径 + 手机嵌入端点 + 会话目录）
B. 端口          —— SANDGLASS_API_PORT / LMS_API_PORT / GLUE_PORT / EDITOR_PORT
C. 派生路径      —— 由 A/B 自动计算（SANDGLASS_SOURCE / RUN_DIR / LOG_DIR / LMS_URL …）
D. 服务参数      —— LMS 做梦频率等
```

密钥不进本文件：
- LMS 密钥 → `$LMS_HOME/.env`（LMS 启动时自读）
- 轻如烟密钥 → `$LIGHT_HOME/scripts/.env`

### 已知的机器级例外（无法配置化，部署时人工处理）

| 文件 | 说明 |
|---|---|
| `living-memory-system-cloud/scripts/lms-api.service` | systemd 单元文件，含绝对路径，安装时 `sed` 替换 |
| `living-memory-system-cloud/scripts/lms_logrotate.conf` | logrotate 配置，含绝对路径，同样按机器替换 |
| OpenClaw gateway 自身（`openclaw.json` 里的 MCP 注册） | 指向各仓库路径，换机器时由 OpenClaw 部署流程处理 |

---

## 4. 部署校验（doctor 检查项）

`./stack_ctl.sh doctor` 逐项检查并输出 ✅/❌：

1. **配置文件**：env.local 是否存在
2. **必需变量**：13 个核心变量是否全部定义
3. **路径存在性**：10 个目录 + FACTS_DICT_PATH + LMS venv/.env + 各服务入口文件
4. **端口状态**：17333/8190/19000/18888 监听情况（空闲=正常未启动）
5. **依赖命令**：python3 / curl / ss / pgrep / setsid / bash

---

## 5. 目录约定

| 用途 | 默认位置 | 变量 |
|---|---|---|
| PID 文件 | `$AGENT_OS_HOME/run/` | `RUN_DIR` |
| 堆栈日志 | `$AGENT_OS_HOME/logs/` | `LOG_DIR` |
| 总线数据（事件流水） | `$AGENT_OS_HOME/iso-sand/data/` | `ISO_SAND_HOME/data` |
| LMS 自身日志 | `$LMS_HOME/logs/` | `LOG_FILE`（lms_ctl 内 `LMS_LOG_FILE` 可覆盖） |

---

## 6. 变更记录

- **2026-08-11（体验层 A-D + 沙漏 P0-1/2/3 部署同步）**
  - 新增 §2.5 体验层部署（重启生效要点 + 新环境变量清单）
  - 全景表标注 /react、sandglass.entry 订阅、WAKE_CHANNEL/SG_* 通道
  - 部署后验证：SYSTEM.md §3.5 新增「部署后 10 分钟验证清单」（不看代码版）
- **2026-08-10（部署统一化重构）**
  - 新建 `env.template`（带注释模板）+ 重写 `env.local`（配置中心）
  - `stack_ctl.sh`：新增 `setup` / `doctor` 命令；SERVICES 全部引用配置变量；删除全部硬编码默认路径
  - `start_all.sh` / `status_all.sh` / `stop_all.sh`：绝对路径默认值 → 相对推导
  - `iso-sand/start_scheduler.sh` / `start_consumer.sh`：生成器路径随 `SCRIPT_DIR` 推导，日志入 `LOG_DIR`（原 /tmp）
  - 轻如烟 6 个自愈脚本 + `session-reset-watchdog.py`：读统一配置，零硬编码
  - LMS `lms_ctl.sh`（PID 目录统一到 `RUN_DIR`）、`fix_pid_probe.sh`（端口读配置）
  - 全部原脚本备份为 `.bak-deploy-unify`
