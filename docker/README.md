# Agent OS Docker 化 — 部署说明（Phase 7）

> 目录自包含说明。总纲见 `../DEPLOYMENT.md` §10。
> 目标：`docker compose up -d` 拉起整套系统（沙漏 / LMS / 胶水 / iso-sand 总线 / 玄鉴可选）。

## 1. 本目录结构

```
docker/
├── docker-compose.yml          # 主编排（5 服务）
├── .env.example                # 机器配置模板：路径 / 宿主端口 / 运行模式（无密钥）
├── .env.local.example          # 环境变量模板：密钥 + 运行配置（无真实 key、无 LAN IP 默认值）
├── .env / .env.local           # 实际配置（gitignore，不入库）
├── .gitignore
├── README.md                   # 本文件
├── sandglass/Dockerfile.sandglass   # 沙漏镜像（path-mirror，无源码 COPY）
├── glue/Dockerfile.glue             # 胶水镜像（python slim + requests，path-mirror）
├── iso-sand/
│   ├── Dockerfile.iso-sand     # 总线镜像（python slim + pyyaml + croniter）
│   ├── launcher.py             # 双进程监督器（scheduler + consumer）
│   ├── tasks.scratch.yaml      # 沙箱验证用任务（心跳每分钟；生产不用）
│   └── scratch_heartbeat.py    # 沙箱心跳（写沙箱 event_bus，绝不碰真实总线）
├── verify/Dockerfile.verify    # 玄鉴镜像（纯 stdlib，path-mirror）
└── verify-data/                # 沙箱验证数据（gitignore；容器写出的测试产物）
```

## 2. 快速开始

```bash
cd "/vol2/1000/AI专用/Agent OS/docker"

# 1) 机器配置
cp .env.example .env
#    · 验证阶段（裸进程仍在跑）：端口改 18190/18191/18192，
#      ISO_SAND_DATA_HOST / LMS_SNAPSHOT_HOST / VERIFY_DATA_HOST 指向 ./verify-data/ 沙箱，
#      ISO_SAND_TASKS_FILE=/docker/iso-sand/tasks.scratch.yaml
#    · 正式切换：保持默认（17333/8190/19000 + 真实数据目录）

# 2) 密钥与运行配置
cp .env.local.example .env.local
#    填 DEEPSEEK_API_KEY（从 living-memory-system-cloud/.env 复制）
#    本机嵌入建议改 LAN：LMS_CLOUD_EMBED_URL / VECTOR_URL =
#      http://192.168.0.103:11435/v1/embeddings   （仅填本地 .env.local，勿入库）

# 3) 启动
docker compose up -d --build
docker compose --profile xuanjian up -d   # 玄鉴可选服务

# 4) 检查
docker compose ps            # 全部 healthy 为佳
curl http://127.0.0.1:17333/api/health    # （正式端口）沙漏
curl http://127.0.0.1:8190/health         # LMS
curl http://127.0.0.1:19000/health        # 胶水
```

## 3. 服务清单

| 服务 | 镜像 | 容器端口 | 宿主端口 | 健康检查 | 依赖 |
|---|---|---|---|---|---|
| sandglass-api | agentos-sandglass | 17333（代码硬编码） | `${SANDGLASS_HOST_PORT:-17333}` | GET /api/health | — |
| lms-api | living-memory-system:latest | 8190 | `${LMS_HOST_PORT:-8190}` | GET /health（90s 预热） | — |
| glue-server | agentos-glue | 19000 | `${GLUE_HOST_PORT:-19000}` | GET /health | lms-api healthy |
| iso-sand | agentos-iso-sand | — | — | /tmp/iso_sand_alive 新鲜度 | glue-server healthy |
| verify-daemon（可选） | agentos-verify | — | — | daemon_audit.log 新鲜度 | iso-sand healthy |

## 4. 关键设计决策

### 4.1 path-mirror（沙漏 / 胶水 / 玄鉴）
组件代码硬编码了宿主绝对路径（如沙漏的 `DB_PATH`、facts 字典路径、sys.path），
红线要求不改核心代码 → 容器内把宿主目录挂载到**相同绝对路径**：

```yaml
volumes:
  - /vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source:/vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source:ro
  - /vol2/1000/AI专用/所有自动化/轻如烟/sandglass:/vol2/1000/AI专用/所有自动化/轻如烟/sandglass
```

镜像不含源码，只提供运行时（python + curl/requests/pyyaml/croniter）。
**因此：SANDBOX_* / GLUE_HOME_DIR / VERIFY_HOME_DIR 等路径不可随意改动**
（除非同步修改组件代码），它们同时是容器内路径。

> 注意：胶水容器除 GLUE_HOME_DIR 外，**还必须挂载 `SANDBOX_SOURCE_DIR`**（沙漏源码，ro）——
> `SandglassVaultAdapter` 会 `sys.path.insert(SANDGLASS_SOURCE)` 后 import `sandglass_vault`，
> 缺该挂载会报 `No module named 'sandglass_vault'`（已踩坑并修复）。

### 4.2 LMS 镜像的一个必要微调
`living-memory-system-cloud/requirements.txt` 新增一行 `requests>=2.31`
（唯一一处组件文件改动，Phase 7 已注释说明）：`core/sensory/cloud_embedder.py`
import requests，而 requirements 原本没有它 → 容器内 CloudEmbedder 导入失败 →
降级 PretrainedEmbedder → HF 不可达 → /chat 500。加依赖后 CloudEmbedder 正常。
（裸进程模式不受影响——宿主 venv 早已装有 requests。）

### 4.2 iso-sand 单容器双进程
scheduler + consumer 强耦合同一数据目录与配置 → 一个容器，`launcher.py` 监督：
任一子进程退出 → 容器 exit(2) → `restart: unless-stopped` 双双重启。
`init: true`（tini）回收子进程防僵尸。healthcheck 靠 launcher 维护的
`/tmp/iso_sand_alive`（仅双进程存活时更新）。

### 4.3 网络：bridge（默认）
- 服务间互连用服务名：glue→`lms-api:8190`；iso-sand 处理器→`glue-server:19000`、`lms-api:8190`。
- 嵌入/向量走外网（隧道域名或 LAN，`.env.local` 配置）；容器出网走 NAT，本机 LAN 可达（已验证）。
- 若遇特殊网络环境（如宿主防火墙限制 bridge 出网），可整栈改 `network_mode: host`，
  但需注意端口与裸进程冲突，且服务名互连失效（改回 localhost）。

### 4.4 密钥与敏感信息
- `DEEPSEEK_API_KEY` 等只经 `env_file: ./.env.local` 注入；镜像内无默认值。
- `.env.local` 不入库（.gitignore）。
- **LAN 内网地址（192.168.0.103）不写入任何会进 Git 的文件**：
  模板默认隧道域名 `https://11435.tdx1146.cc/v1/embeddings`；
  本机部署在本地 `.env.local` 改 LAN 直连（更快），他机部署保持隧道。

## 5. 数据卷一览（bind mount）

| 容器 | 宿主目录（.env 可改） | 容器路径 | 读写 |
|---|---|---|---|
| sandglass-api / glue-server | `SANDBOX_DATA_DIR`（轻如烟/sandglass） | 同绝对路径 | rw |
| sandglass-api | `SANDBOX_SOURCE_DIR`（sandglass_source） | 同绝对路径 | ro |
| sandglass-api | `FACTS_MEMORY_DIR`（workspace/memory） | 同绝对路径 | ro |
| lms-api | `LMS_SNAPSHOT_HOST`（LMS snapshots） | /app/snapshots | rw |
| lms-api | `LMS_CACHE_HOST`（docker/data/lms-cache） | /root/.cache | rw |
| glue-server | `GLUE_HOME_DIR`（memory-integration-layer） | 同绝对路径 | ro |
| iso-sand | `ISO_SAND_HOME_DIR`（iso-sand 根） | /app/iso-sand | ro |
| iso-sand | `ISO_SAND_DATA_HOST`（iso-sand/data） | /app/iso-sand/data | rw |
| iso-sand | `./iso-sand`（本目录 launcher 等） | /docker/iso-sand | ro |
| verify-daemon | `VERIFY_HOME_DIR`（同构沙盘根）+ `KERNEL_SPEC_DIR` | 同绝对路径 | ro |
| verify-daemon | `VERIFY_DATA_HOST`（同构沙盘/data） | 同绝对路径（嵌套 rw 覆盖） | rw |

## 6. 沙箱验证模式（不动裸进程）

裸进程仍在跑时，用沙箱模式验证容器：

```bash
# .env 中：
SANDGLASS_HOST_PORT=18190
LMS_HOST_PORT=18191
GLUE_HOST_PORT=18192
ISO_SAND_DATA_HOST=./verify-data/iso-sand-data   # 沙箱总线（勿拷贝真实 event_bus）
LMS_SNAPSHOT_HOST=./verify-data/lms-snapshots    # 沙箱快照（从真实 snapshots 复制）
VERIFY_DATA_HOST=./verify-data/xuanjian-data     # 沙箱玄鉴数据
ISO_SAND_TASKS_FILE=/docker/iso-sand/tasks.scratch.yaml
```

- 沙箱 event_bus 保持**空文件**启动：避免消费者处理真实事件触发副作用（处理器会调
  glue/LMS/audit）。
- 沙箱心跳任务每分钟写一次 `sandglass.heartbeat`（消费者不订阅该类型，无副作用）。
- 沙箱玄鉴 data/ 为空 → 守护进程空闲（写 audit 启动日志），与裸 verify 无 pid 竞争。

## 7. 镜像构建备注

- 基础镜像：`python:3.11-slim`。本机 registry-mirror `docker.fnnas.com` 失效（401），
  直连 docker.io 被墙 → 用可用源拉取后 retag：
  ```bash
  docker pull docker.m.daocloud.io/library/python:3.11-slim
  docker tag docker.m.daocloud.io/library/python:3.11-slim python:3.11-slim
  ```
- LMS 镜像（复用 living-memory-system/Dockerfile）：多阶段，torch CPU 191MB wheel，
  首次构建实测约 25 分钟（主要耗时：Debian apt 装 curl/git ~9 分钟 + torch 下载）。
  已确认 pytorch.org CPU index 本机可达。镜像 1.62GB。
- 轻量镜像（sandglass/glue/iso-sand/verify）：秒级构建。

## 8. 与裸进程模式切换

```bash
# 裸 → 容器
cd "/vol2/1000/AI专用/Agent OS" && bash stop_all.sh
cd docker && docker compose up -d --build

# 容器 → 裸
cd "/vol2/1000/AI专用/Agent OS/docker" && docker compose down
cd .. && bash start_all.sh
```

## 9. 给后来者的备注

1. **LAN 嵌入地址怎么配**：本机填 `http://192.168.0.103:11435/v1/embeddings`（0.03s）；
   他机/外网填隧道 `https://11435.tdx1146.cc/v1/embeddings`（~1.5s）。改 `.env.local`
   的 `LMS_CLOUD_EMBED_URL` 与 `VECTOR_URL` 两处。
2. **密钥只走 env**：`docker/.env.local` 是唯一注入点；构建上下文（各子目录）不含任何密钥。
3. **数据卷位置**：见 §5；全部 bind mount 指向宿主真实目录，`down` 不删数据。
4. **端口冲突**：容器内端口固定（17333/8190/19000 由代码/镜像决定），宿主映射可改。
   验证阶段用 18190/18191/18192 避开裸进程。
5. **玄鉴是可选服务**（profile: xuanjian），因其与裸 verify 共用 data/（pid 竞争）。
6. **沙漏 17333 的 facts_lookup** 读的是 `workspace/memory/facts.dict.md`（ro 挂载），
   与本机 OpenClaw 工作区同源。
