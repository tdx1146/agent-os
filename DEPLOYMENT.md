# DEPLOYMENT.md — Agent OS 部署手册（Phase 6 部署一致性工程）

> ⚠️ 2026-08-10 起：全局部署统一化已重构，**新机器部署请先看 [DEPLOY-GLOBAL.md](DEPLOY-GLOBAL.md)**
> （配置中心 env.local + stack_ctl.sh setup/doctor 一键校验）。本文保留 Phase 6 细节。
>
> 更新时间：2026-08-04（Phase 6）
> 目标：从零到一可复现部署，全功能不降级。
> 一键运维：`start_all.sh` / `stop_all.sh` / `status_all.sh`（本目录）。
> 配置单：`env.template`（复制为 `env.local` 填值，start_all.sh 自动加载）。

---

## 1. 前置依赖清单

| 依赖 | 版本/要求 | 说明 |
|---|---|---|
| Python | 3.11.x（本机 3.11.2） | 沙漏 / LMS / 胶水层 / iso-sand 全部使用 |
| git | 任意 | 拉取仓库 |
| Node.js | v24（本机 v24.15.0） | 手机网关 mcp-server.js / openclaw-proxy（非必须） |
| 手机 Ollama | bge-m3 模型，端口 11435 | 向量嵌入服务（`http://192.168.0.103:11435/v1/embeddings`，LAN 直连最快；备选域名隧道 `https://11435.tdx1146.cc/v1/embeddings`） |
| DeepSeek API Key | 有 | 存于 LMS `.env`（`DEEPSEEK_API_KEY`），勿写入 env.template |
| NAS 本机网络 | 手机与 NAS 同 LAN | 192.168.0.103 需可达 |
| OpenClaw Gateway | 运行中 | MCP 注册 lms-memory / lms-http / shouji-memory |

> ⚠️ **嵌入模式**：LMS 必须 `LMS_EMBEDDER=cloud`。HF 不可达，严禁切 local。

---

## 2. 仓库清单（clone 地址 + 本地位置）

| 仓库 | clone 地址（脱敏） | 本地位置 |
|---|---|---|
| NexSandglass 沙漏 | `https://github.com/sixgodgit/NexSandglass-Agent-DedicatedMemory.git` | `/vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source` |
| 活体记忆 LMS | `https://github.com/tdx1146/living-memory-system.git`（remote 内嵌 token，勿外泄） | `/vol2/1000/AI专用/living-memory-system-cloud` |
| 胶水层 | `https://github.com/tdx1146/memory-integration-layer.git`（remote 内嵌 token） | `/vol2/1000/AI专用/memory-integration-layer` |
| iso-sand 事件总线 | 无独立 remote（随 Agent OS 目录） | `/vol2/1000/AI专用/Agent OS/iso-sand` |
| 同构沙盘（玄鉴） | 无 remote | `/vol2/1000/AI专用/AgentOS-IsoSand/同构沙盘` |
| 丰碑网络 | 无 remote | `/vol2/1000/AI专用/丰碑网络` |

---

## 3. 配置步骤（cp env.template → 填值 → 各 .env）

```bash
cd "/vol2/1000/AI专用/Agent OS"
cp env.template env.local      # 填真实值（默认值已适配本机）
```

各服务实际读取的配置：

1. **沙漏**：`start_all.sh` 导出 `NEXSANDBASE_HOME` + `SANDGLASS_SOURCE`。
   - `NEXSANDBASE_HOME=/vol2/1000/AI专用/所有自动化/轻如烟/sandglass`（**必须**，否则 `sandglass_paths._NB` 落到空 `~/.neurobase`）
   - 数据文件：`sandglass.txt` / `sandglass.db` / `shadow_sand.db` / `decision_particles.txt` / `persona/` / `archive/`
2. **LMS**：`/vol2/1000/AI专用/living-memory-system-cloud/.env`
   - `LMS_EMBEDDER=cloud`、`LMS_CLOUD_EMBED_URL=http://192.168.0.103:11435/v1/embeddings`、`LMS_CLOUD_EMBED_MODEL=bge-m3`、`LMS_CLOUD_EMBED_DIM=1024`
   - `DREAM_IDLE_THRESHOLD=300`（Phase 5 已调低做梦频率）
   - `DEEPSEEK_API_KEY=<密钥>`（不写进 env.template/env.local）
3. **胶水层**：`/vol2/1000/AI专用/memory-integration-layer/.env`（glue_server 启动时自读）
   - `SANDGLASS_SOURCE` / `NEXSANDBASE_HOME` / `LMS_URL=http://localhost:8190` / `VECTOR_URL=http://192.168.0.103:11435/v1/embeddings`
4. **iso-sand**：`iso-sand/start_scheduler.sh` / `start_consumer.sh` 自含路径；丰碑 audit 低频化在 `src/handlers.py` 的 `AuditTaskCompleteHandler.rate_limit = 1800.0`
5. **玄鉴**：`verify_daemon.py` 自含路径（`KERNEL_SPEC_DIR=/vol2/1000/AI专用/AgentOS-IsoSand/内核层规范`）
6. **facts.dict.md**（17333 `facts_lookup` 读）：`/vol1/@apphome/trim.openclaw/data/workspace/memory/facts.dict.md`
   ```bash
   cp "/vol2/1000/AI专用/所有自动化/轻如烟/scripts/facts.dict.md" \
      "/vol1/@apphome/trim.openclaw/data/workspace/memory/facts.dict.md"
   ```

---

## 4. 启动 / 停止 / 状态

```bash
cd "/vol2/1000/AI专用/Agent OS"
bash start_all.sh    # 按依赖顺序：沙漏17333 → LMS 8190 → 胶水19000 → iso-sand → 玄鉴
bash stop_all.sh     # 逆序停止，PID 文件 + 端口双保险，停止后确认端口释放
bash status_all.sh   # 进程 + 端口 + health 端点一览
```

- 日志：`Agent OS/logs/*.log`（sandglass_http_api / lms_api / glue_server / verify_daemon）
- PID：`Agent OS/run/*.pid`（stop_all 用；玄鉴另在 `同构沙盘/data/daemon.pid`）
- 开机自启：crontab 已含 `@reboot sleep 20 && bash /vol2/1000/AI专用/Agent OS/start_all.sh`（systemd user bus 不可用，故用 crontab）
- 服务被中断时也能自愈：`*/5 * * * *` health-check.sh（已修正路径）、`*/10 * * * *` pulse-cron.sh（沙漏自治脉冲）

---

## 5. MCP 注册（OpenClaw）

```bash
openclaw mcp set lms-memory '{"command":"/vol2/1000/AI专用/living-memory-system-cloud/.venv/bin/python","args":["/vol2/1000/AI专用/living-memory-system-cloud/mcp_memory_server.py"],"cwd":"/vol2/1000/AI专用/living-memory-system-cloud","env":{"LMS_EMBEDDER":"cloud","LMS_CLOUD_EMBED_URL":"http://192.168.0.103:11435/v1/embeddings","LMS_CLOUD_EMBED_MODEL":"bge-m3","LMS_CLOUD_EMBED_DIM":"1024","LMS_SNAPSHOT_DIR":"/vol2/1000/AI专用/living-memory-system-cloud/snapshots"}}'

openclaw mcp set lms-http '{"command":"/vol2/1000/AI专用/living-memory-system-cloud/.venv/bin/python","args":["/vol2/1000/AI专用/living-memory-system-cloud/lms_http_mcp.py"],"cwd":"/vol2/1000/AI专用/living-memory-system-cloud","env":{"LMS_EMBEDDER":"cloud","LMS_CLOUD_EMBED_URL":"http://192.168.0.103:11435/v1/embeddings","LMS_CLOUD_EMBED_MODEL":"bge-m3","LMS_CLOUD_EMBED_DIM":"1024","LMS_SNAPSHOT_DIR":"/vol2/1000/AI专用/living-memory-system-cloud/snapshots"}}'

openclaw mcp set shouji-memory '{"command":"/vol2/1000/AI专用/living-memory-system-cloud/.venv/bin/python","args":["/vol2/1000/AI专用/所有自动化/轻如烟/shouji_memory_mcp.py"]}'
```

> 链路：OpenClaw → shouji_memory_mcp.py（stdio 桥）→ `https://shouji.tdx1146.cc/tools/{name}`（手机网关）→ `NAS_API=192.168.0.149:17333`（本机沙漏 API）。

---

## 6. 验证清单

```bash
# 1. 沙漏 API（4 端点全要真实结果）
curl http://127.0.0.1:17333/api/health                       # sandglass_count>0
curl -X POST http://127.0.0.1:17333/api/memory_search     -H 'Content-Type: application/json' -d '{"query":"总线工程","limit":3}'
curl -X POST http://127.0.0.1:17333/api/embedding_search  -H 'Content-Type: application/json' -d '{"query":"总线工程","limit":3}'
curl -X POST http://127.0.0.1:17333/api/facts_lookup      -H 'Content-Type: application/json' -d '{"keyword":"轻如烟","limit":3}'
curl -X POST http://127.0.0.1:17333/api/sandglass_query   -H 'Content-Type: application/json' -d '{"query":"总线工程","limit":3}'

# 2. LMS / 胶水
curl http://127.0.0.1:8190/health                           # {"status":"ok",...}
curl http://127.0.0.1:19000/health                          # backends 三后端 healthy

# 3. 玄鉴
cat /vol2/1000/AI专用/AgentOS-IsoSand/同构沙盘/data/daemon.pid   # 进程存活
tail -1 /vol2/1000/AI专用/AgentOS-IsoSand/同构沙盘/data/daemon_audit.log

# 4. 一次端到端记忆写入（沙漏 L1）
cd /vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source
NEXSANDBASE_HOME=/vol2/1000/AI专用/所有自动化/轻如烟/sandglass python3 -c "
from sandglass_log import log_message
log_message('部署验证：端到端写入 OK')
"
tail -1 /vol2/1000/AI专用/所有自动化/轻如烟/sandglass/sandglass.txt
```

---

## 7. 故障排查表

| 症状 | 可能原因 | 处理 |
|---|---|---|
| 17333 `/api/health` 返回 `sandglass_count: 0` | 进程启动时未带 `NEXSANDBASE_HOME` | 用 start_all.sh 重启（脚本自动导出）；勿裸跑 `python3 sandglass_http_api.py` |
| embedding_search / sandglass_query 返回 `[]` | 同上（`_NB` 落到空 `~/.neurobase`） | 同上；检查 `Agent OS/logs/sandglass_http_api.log` |
| facts_lookup 报 No such file | `workspace/memory/facts.dict.md` 缺失 | 从 `轻如烟/scripts/facts.dict.md` 复制（见 §3.6） |
| LMS 8190 health 失败 | 启动慢（嵌入模型初始化）或 `.env` 未 source | start_all.sh 已带 40s 轮询；手动：`cd LMS && set -a && . ./.env && set +a && .venv/bin/python -m api.run` |
| 嵌入空 / 报错 | 手机 Ollama 不可达 | `curl http://192.168.0.103:11435/v1/embeddings` 测通；隧道版 `https://11435.tdx1146.cc` 更慢但可用 |
| 胶水层 backends 某后端 unhealthy | 对应服务未起 | status_all.sh 定位；先启依赖（沙漏→LMS） |
| 手机网关（shouji）不可达 | Cloudflare 隧道/手机离线 | MCP 工具 fail-open 返回错误文本；本机 17333 直连不受影响 |
| 丰碑 audit_bridge.log 每 5 分钟刷 pending | 心跳事件触发 audit（Phase 6 已限流） | 正常：`rate_limit=1800` 后 30 分钟最多 1 条 |
| 玄鉴 daemon.pid 存在但进程死 | 被误杀/崩溃 | `bash start_all.sh`（自动拉起）；看 `logs/verify_daemon.log` |
| 重启后 MCP 工具报错 | Gateway 未重启加载新配置 | `openclaw gateway restart`（内存搜索禁用等配置需重启生效） |

---

## 8. 测试说明

```bash
# 胶水层（81 用例）
cd /vol2/1000/AI专用/memory-integration-layer
.venv/bin/python -m pytest -q          # 81 passed

# 活体记忆 LMS（598 个 test 函数 / 约 672 用例；导入 torch 慢，耐心等）
cd /vol2/1000/AI专用/living-memory-system-cloud
.venv/bin/python -m pytest -q          # 需要先 source .env（嵌入走 cloud）

# 沙漏（NexSandglass 自带 demo/ 测试脚本）
cd /vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source
NEXSANDBASE_HOME=/vol2/1000/AI专用/所有自动化/轻如烟/sandglass python3 -m pytest demo/ -q 2>/dev/null || echo "demo 为脚本型测试，无 pytest"

# iso-sand 事件总线（handlers.py 内建自测）
cd /vol2/1000/AI专用/Agent OS/iso-sand
PYTHONPATH=src python3 src/handlers.py
```

---



## 9. Phase 6 遗留 TODO

- [ ] **facts.dict.md**：已找回并复制到 `workspace/memory/facts.dict.md`（源自 `轻如烟/scripts/facts.dict.md`，92KB，2026-06-22 版本）。若 dandan 需要更新版事实字典，另行重建。
- [ ] **gateway 重启**：`memorySearch.enabled=false` 已写入 openclaw.json，需 `openclaw gateway restart` 生效（顺带清理 MCP 旧批次进程）。
- [ ] **LMS .env 嵌入地址**：当前为 `https://11435.tdx1146.cc/v1/embeddings`（隧道，可用但慢 ~1.5s）；`env.template` 标准值为 LAN `http://192.168.0.103:11435`（0.03s）。下次 LMS 重启时可统一。
- [ ] **comprehensive_offset sample=0**：`persona/decision-log.jsonl` 不存在（无决策数据），功能正常、无数据；待沙漏开始记录决策后自然有值。
- [ ] **玄鉴 zhaojian-monitor cron**：daemon_audit.log 显示存在 30 分钟级外部复核 cron（旧 PID 3183279 已死，复核记录停留在 12:51）。未找到该 cron 条目归属（不在 trim.openclaw crontab），如需要可在后续补回。

---

## 10. Docker 化部署（Phase 7，2026-08-05）

> 目标：后来者 `docker compose up -d` 拉起整套系统（沙漏 17333 / LMS 8190 / 胶水 19000 / iso-sand 总线 / 玄鉴可选）。
> 编排目录：`Agent OS/docker/`（自包含说明见 `docker/README.md`）。
> 本机：Docker 28.5.2 + Compose v2.40.3；镜像基础层需镜像加速（见下方 FAQ）。

### 10.1 两种运行模式

| 模式 | 说明 | 使用时机 |
|---|---|---|
| **裸进程**（默认现状） | `bash start_all.sh` 拉起全部进程 | 日常现状（Phase 6 已验证） |
| **容器**（Docker） | `docker compose up -d` | 后续切换目标；验证阶段已跑通 |

> ⚠️ 两种模式**不能同时跑同一服务**（端口/数据竞争）。切容器前必须先 `bash stop_all.sh`。
> 容器化验证阶段用临时宿主端口 18190/18191/18192 + 沙箱数据目录，可与裸进程共存（已实测）。

### 10.2 快速开始

```bash
cd "/vol2/1000/AI专用/Agent OS/docker"
cp .env.example .env            # 机器配置：路径/端口（验证阶段端口改 18190/18191/18192）
cp .env.local.example .env.local  # 密钥 + 运行配置，填 DEEPSEEK_API_KEY（从 LMS .env 复制）
# 本机嵌入建议：.env.local 中 LMS_CLOUD_EMBED_URL / VECTOR_URL 填 LAN 直连
#   http://192.168.0.103:11435/v1/embeddings（仅本机，勿入库）；默认模板给隧道域名

docker compose up -d --build     # 全系统启动（首次构建 LMS 镜像约 10-20 分钟，torch CPU 190MB）
# 玄鉴可选服务：
docker compose --profile xuanjian up -d

docker compose ps                # 状态（全 healthy 为佳）
docker compose logs -f <service> # 看日志
```

### 10.3 端口与互连（容器模式）

| 服务 | 容器内 | 宿主映射（.env 可改） | 说明 |
|---|---|---|---|
| sandglass-api | 17333（代码硬编码） | `${SANDGLASS_HOST_PORT:-17333}` | path-mirror 挂载宿主源码+数据 |
| lms-api | 8190 | `${LMS_HOST_PORT:-8190}` | 复用 living-memory-system Dockerfile |
| glue-server | 19000 | `${GLUE_HOST_PORT:-19000}` | 容器内连 `lms-api:8190` |
| iso-sand | — | — | 无 HTTP；launcher 双进程 + 文件心跳健康检查 |
| verify-daemon | — | — | 可选（profile: xuanjian），文件型健康检查 |

容器内互连（bridge 网络，服务名）：glue→`lms-api:8190`；iso-sand 处理器→`glue-server:19000` + `lms-api:8190`（compose 已配 `LMS_URL` / `GLUE_SERVER_URL`）。

### 10.4 数据卷（bind mount，全部指向宿主真实目录）

| 容器 | 宿主目录（.env 可改） | 容器路径 | 读写 |
|---|---|---|---|
| sandglass-api / glue-server | `所有自动化/轻如烟/sandglass` | 同绝对路径（path-mirror） | rw（vault 重建 idx） |
| sandglass-api | `轻如烟/sandglass_source` + `workspace/memory` | 同绝对路径 | ro |
| lms-api | `living-memory-system-cloud/snapshots` | `/app/snapshots` | rw |
| iso-sand | `Agent OS/iso-sand/data` | `/app/iso-sand/data` | rw |
| verify-daemon | `同构沙盘/data`（嵌套 rw）+ 项目根/内核规范 ro | 同绝对路径 | rw/ro |

> 沙漏 / 胶水 / 玄鉴采用 **path-mirror**：组件代码硬编码绝对路径（红线：不改核心代码），
> 因此容器内挂载与宿主**相同的绝对路径**，所有硬编码原样生效。镜像不含源码。

### 10.5 密钥与安全

- 密钥只经 `docker/.env.local`（env_file）注入：`DEEPSEEK_API_KEY` 等；**不进镜像、无默认值**。
- `.env.local` / `.env` / `verify-data/` 已被 `docker/.gitignore` 忽略，禁止提交。
- **LAN 内网地址（192.168.0.103）不写入任何会进 Git 的文件**；模板默认给隧道域名 `https://11435.tdx1146.cc/v1/embeddings`，本机部署可改 LAN 直连。

### 10.6 裸进程 ↔ 容器切换步骤

```bash
# 裸进程 → 容器
cd "/vol2/1000/AI专用/Agent OS"
bash stop_all.sh                                  # 1. 停裸进程（必须，端口/数据竞争）
cd docker
docker compose up -d --build                      # 2. 起容器（.env 端口保持 17333/8190/19000）
docker compose ps && curl http://127.0.0.1:17333/api/health  # 3. 验证

# 容器 → 裸进程
cd "/vol2/1000/AI专用/Agent OS/docker"
docker compose down                                # 1. 停容器（数据卷不删）
cd .. && bash start_all.sh                         # 2. 起裸进程
```

### 10.7 常见问题（Docker）

| 症状 | 原因 | 处理 |
|---|---|---|
| `docker compose up` 拉 python 基础镜像 401/超时 | 本机 registry-mirror `docker.fnnas.com` 失效，直连 docker.io 被墙 | 用可用镜像源拉取后 retag：`docker pull docker.m.daocloud.io/library/python:3.11-slim && docker tag docker.m.daocloud.io/library/python:3.11-slim python:3.11-slim`（已验证可行） |
| LMS 镜像构建很慢 | torch CPU wheel 191MB + Debian apt（中国网络） | 首次约 10-20 分钟；后续有缓存。`tail -f /tmp/lms-docker-build.log` 或 `docker compose build lms-api` 看进度 |
| iso-sand 容器健康但 event_bus 无心跳 | croniter 缺失（旧镜像） | 已修复：Dockerfile.iso-sand 安装 pyyaml+croniter；`docker compose build iso-sand && up -d --force-recreate iso-sand` |
| 容器内访问 LAN 嵌入失败 | bridge NAT 或手机离线 | 先测 `curl -X POST http://192.168.0.103:11435/v1/embeddings`；改用隧道域名 |
| 玄鉴容器与裸 verify 抢 daemon.pid | 同 data/ 目录双写 | 玄鉴用 profile 隔离；切容器前 `bash stop_all.sh` |
| 想验证又不想停裸进程 | 端口/数据竞争 | 用沙箱模式：`.env` 端口改 18190/18191/18192，`ISO_SAND_DATA_HOST`/`LMS_SNAPSHOT_HOST`/`VERIFY_DATA_HOST` 指向 `verify-data/`（见 README） |

### 10.8 Phase 7 遗留 TODO

- [x] **验证阶段发现并修复（Phase 7 实测）**：
  - `living-memory-system-cloud/requirements.txt` 新增 `requests>=2.31`（CloudEmbedder 依赖，容器内缺失会降级 Pretrained→HF 不可达→/chat 500）。这是 Phase 7 唯一一处组件文件改动，已注释说明。
  - glue-server 需挂载 `SANDBOX_SOURCE_DIR`（沙漏源码 ro），否则 `No module named 'sandglass_vault'`（已修复）。
  - iso-sand 镜像需 `pyyaml + croniter`（croniter 缺失时调度器线程静默死亡，无心跳）（已修复）。
  - 容器→LAN（192.168.0.103:11435）经 bridge NAT 实测可达（200, dim=1024）；隧道域名同样可达。
- [ ] **registry-mirror**：`/etc/docker/daemon.json` 的 `docker.fnnas.com` 已失效（401），建议换 `docker.m.daocloud.io` 或 `docker.1panel.live` 并 `systemctl restart docker`（改完直连拉取即可，无需 retag）。
- [ ] **LMS 镜像体积**：torch CPU 镜像约 1.62GB（builder 含 build-essential）；后续可尝试精简 layer 优化；Dockerfile 中 `ENV DEEPSEEK_API_KEY=` 空默认值可改造成 build-time 注入（当前空值安全，运行时由 env_file 覆盖）。
- [ ] **iso-sand 生产切换**：切容器前确认 `tasks.yaml` 心跳频率（每 5 分钟）与裸模式一致；`bus_heartbeat` 在容器内每分钟一次仅沙箱配置。
- [ ] **audit.task_complete 处理器**：`/vol2/1000/AI专用/丰碑网络/code/core/audit.py` 在本机不存在（裸模式同样报错，死信隔离不阻断总线）；如需审计功能需补 audit.py 或改 handler。
- [ ] **玄鉴数据源**：`同构沙盘/data/operation_log.jsonl` 目前不存在（iso-sand 的 operation_log 写在 `iso-sand/data/`），玄鉴容器空闲等待；若需打通，需将两处 operation_log 指向同一文件（未来 Phase）。

---

---
