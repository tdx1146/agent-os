# 🔍 轻如烟妹妹实例侦察报告

> 生成时间：2026-06-25 20:33 CST
> 侦察方式：SSH 密码直连 + 本地配置分析

---

## 1. 已获得的妹妹信息

### 1.1 基础环境

| 项目 | 值 |
|------|-----|
| 主机名 | `dandan`（位于 jiali.tdx1146.com） |
| 网络 IP | IPv6: `240e:3a1:646b:e990::1000`（无 IPv4 A 记录） |
| 操作系统 | Linux qh 6.18.18-trim x86_64 |
| 内网 VLAN | 192.168.x.x（可能共享二层） |
| 内存 | 7.6GB 总 / 4.2GB 可用 |
| 磁盘 | 根分区 32G（44% 已用）/ vol1 80G（30% 已用） |
| 运行时长 | 2天22小时 |
| SSH 密码 | `xiaoxiao1983620` ✅ 已验证可用 |

### 1.2 OpenClaw 状态

| 项目 | 值 |
|------|-----|
| **Gateway 版本** | **2026.6.9** |
| Gateway 端口 | `17587`（loopback 仅本地） |
| Gateway Token | `clw_fnos_2026_17587` |
| 运行时 | 用 **bun** 启动（`bun /vol1/@appcenter/trim.openclaw/server/index.js`）|
| Gateway 进程 | PID 656637（6月24日启动，已运行60分钟CPU） |
| bun 进程 | PID 656468（6月24日启动） |
| Dashboard URL | `http://127.0.0.1:17587/app/trim-openclaw/default/` |
| 连接状态 | Connectivity probe: OK, Capability: admin-capable |

### 1.3 模型配置

| 提供商 | API Key 来源 | 是否可用 |
|--------|------------|---------|
| **DeepSeek V4 Flash/Pro** | `sk-aacf96fb58c24be08d62ea19d5d84eb0`（硬编码） | ✅ 可用 |
| **Astron2 (code-latest)** | `0fae64817f866ced38403274c0b7432b:YjVhMDkzMzQxMGIxOGYxNDk5YTVhOWM1`（硬编码） | ✅ **默认主模型** |
| **Astron Coding Plan** | `${ASTRON_API_KEY}`（环境变量） | ⚠️ 需确认 env 是否有值 |
| **混元 (hy3-preview)** | `${HUNYUAN_API_KEY}`（环境变量） | ⚠️ 需确认 env 是否有值 |
| **智谱 (glm-5.2)** | `${ZHIPU_API_KEY}`（环境变量） | ⚠️ 需确认 env（含图片模型） |

**Agent 默认模型链：**
```json
{
  "primary": "astron2/astron-code-latest",
  "fallbacks": ["deepseek/deepseek-v4-flash", "混元/hy3-preview", "astroncodingplan/astron-code-latest"]
}
```

**子代理模型（subagents）：** `astroncodingplan/astron-code-latest`

### 1.4 运行中的服务

| 服务 | 端口 | 状态 |
|------|------|------|
| OpenClaw Gateway | 17587 (loopback) | ✅ 运行中 |
| OpenClaw Agent Runtime | — | ✅ 运行中 |
| Hermes Dashboard | 8082 (0.0.0.0) | ✅ 运行中 |
| Hermes CLI Gateway | — | ✅ 运行中 |
| Nanobot Gateway | — | ✅ 运行中（PID 3095998，在 /vol2/） |
| **edit-web.py（编辑器）** | **18888** | ❌ **未运行** |
| **inject 端点 (/api/inject)** | **18888** | ❌ **未运行**（依赖 edit-web） |
| **MCP Server** | — | ❌ **未运行** |
| **Sandglass MCP Daemon** | — | ❌ **未运行** |

### 1.5 沙漏（Sandglass）状态

| 项目 | 值 |
|------|-----|
| 路径 | `/vol1/轻如烟/轻如烟/sandglass/` |
| 模式 | `work`（工作中） |
| 记录数 | 257 行（sandglass.txt） |
| 数据库 | 53KB（sandglass.db，最近更新 Jun 16） |
| 索引 | 21KB（sandglass.idx，最近更新 Jun 23） |
| MCP Daemon | 未运行（sandglass_source 目录存在，但未启动） |

### 1.6 定时任务（Cron）

| Cron 名称 | 调度 | 状态 | 模型 |
|-----------|------|------|------|
| 轻如烟自愈检查 | every 1h | ✅ ok | — |
| 消化循环 | every 6h | ✅ ok | astroncodingplan |
| 🌫️ 轮感归档（每6h） | cron 0 */6 * * * | ❌ **error** | — |
| 武器库对线 | cron 0 2-8/2 * * * | ❌ **error** | astroncodingplan |
| 静默维护 | every 6h | ✅ ok | — |
| Memory Dreaming | cron 0 3 * * * | ✅ ok | — |
| 晨报 | cron 0 7 * * * | ⚠️ skipped | — |
| 晨报v2 | cron 0 7 * * * | ❌ **error** | astroncodingplan |

> 注意：部分 cron 航 error 状态，可能因为 model（astroncodingplan）或 API key 问题。

### 1.7 同机器上的其他进程

| 进程 | 备注 |
|------|------|
| Hermes Agent | 双进程（dashboard + gateway）|
| Nanobot Gateway | 位于 `/vol2/1000/AI专用/Nanobot/` |
| trim_open_gateway | 系统级 Web 网关（root 进程） |
| PostgreSQL | 运行中（端口 5432，Open Gateway 使用） |

---

## 2. 未获得的信息（和为什么）

| 信息 | 原因 |
|------|------|
| **MCP Server 详细配置** | MCP server 未启动，无法查询运行时状态；配置文件 `/vol1/轻如烟/轻如烟/scripts/dandan-mcp-server-active.mjs` 存在但未注册到 Gateway |
| **环境变量中的 API Keys** | 无法在 SSH session 中查看 `env`（需要 sudo/root）；混元、智谱、Astron 的 key 存于环境变量 |
| **Gateway MCP 注册** | `openclaw.json` 未看到 `mcp` 段输出（可能没配 MCP servers） |
| **VERSION 文件** | 妹妹机器上的 `/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/VERSION` 不存在；妹妹的实际工作目录是 `/vol1/轻如烟/轻如烟/`，该目录下没有 `VERSION` 文件 |
| **近期记忆** | 妹妹的记忆文件到 6月11日为止，最近14天没有更新（可能 session 被重置或 idle 超时） |
| **妹妹的 MEMORY.md** | 最后修改 6月22日，但内容可能是旧的 |
| **QH → JL HTTP 连接** | `jiali.tdx1146.com` 只解析到 IPv6 地址，但 qh 机器（192.168.2.100）可能无法直接访问 IPv6；需要确认内网 IPv4 地址绕过 |
| **桑拿/NFS 共享** | 妹妹的 `/vol1/轻如烟/轻如烟/` 与 qh 的 `/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/` 看起来是不同路径（不同挂载点），不是同一个 NFS 共享 |

---

## 3. 妹妹是否适合承载审计任务

### ✅ 优势

1. **硬件资源充足** — 4.2GB 可用 RAM，57GB 可用磁盘，完全能跑轻量审计
2. **OpenClaw 运行中** — 2026.6.9 稳定版，无需再部署
3. **多模型可用** — DeepSeek（主）、Astron（代码型）、混元、智谱，覆盖审计所需
4. **SSH 通道畅通** — 密码 `xiaoxiao1983620` 已验证，可直连
5. **已有的基础设施** — sandglass 数据、cron 调度、nanobot 网关、Hermes agent
6. **独立实例** — 和 qh 完全隔离，审计任务不会干扰 qh 主会话

### ⚠️ 风险/注意事项

1. **编辑器/inject 未启动** — 最关键的跨实例通信入口挂了。需要先启动 edit-web.py 才能通过 HTTP inject 发任务
2. **memorySearch 已禁用** — `"enabled": false`，妹妹当前没有语义搜索能力
3. **compaction.memoryFlush 已禁用** — 不自动记忆沉淀
4. **部分 cron 报 error** — 武器库对线和轮感归档持续 error，可能表示环境有问题
5. **没有 MCP 服务器在运行** — 需要部署或配置才能使用 `dandan__` 系列工具
6. **IPv6 单栈问题** — jiali.tdx1146.com 只有 AAAA 记录，需要确认 qh→jl 的 IPv6 连通性
7. **最近久未活跃（6月11日后几乎无更新）** — 可能需要重新引导妹妹上线

### 结论：**适合，但有前提条件**

妹妹完全有资源承载审计任务。但需要先解决以下两项：

1. **启动 edit-web.py** → 恢复 inject 通信
2. **确认网络连通性** → 确保 qh→jl 能 HTTP 互通（IPv4 内网 IP 或 IPv6）

---

## 4. 建议的接入方式

### 方式 A：SSH Inject 通道（推荐，最稳定）

```
qh → SSH (xiaoxiao1983620) → jiali.tdx1146.com → 执行命令/脚本
```

**优点：** 已验证可用，不依赖任何 HTTP 服务
**缺点：** 仅限于文件操作和命令执行，不能双向聊天

**用法示例：**
```bash
sshpass -p 'xiaoxiao1983620' ssh tdx1146@jiali.tdx1146.com "你的命令"
```

### 方式 B：恢复 inject HTTP 通道（可聊天）

先 SSH 进去启动编辑器：
```bash
sshpass -p 'xiaoxiao1983620' ssh tdx1146@jiali.tdx1146.com \
  "cd /vol1/轻如烟/轻如烟 && python3 edit-web.py &"
```

之后可通过 HTTP POST 发消息：
```bash
curl -X POST http://jiali.tdx1146.com:18888/api/inject \
  -d '{"message":"妹妹，有审计任务。"}'
```

### 方式 C：MCP 调用（需要额外部署）

1. SSH 到妹妹，注册 MCP server 到 Gateway
2. 配置 `openclaw.json` 的 `mcp.servers` 段
3. 重启 Gateway 生效

### 方式 D：文件共享（单向，仅用于传递审计数据）

由于 `/vol1/@team/` 路径在两台机器上不共享同一存储（不同路径结构），不能直接用文件共享。替代方案：

- SSH SCP 传输审计数据
- 或者通过 MCP 的文件操作工具

### 推荐方案

| 阶段 | 接入方式 | 理由 |
|------|---------|------|
| **短期（立即）** | SSH inject 通道（方式 A） | 不需要任何前置条件，已验证可行 |
| **中期（1-2天）** | 恢复 edit-web.py（方式 B） | 启动后即可双向发送消息 |
| **长期** | MCP 部署（方式 C） | 最灵活，支持完整工具调用 |

---

## 附录 A：SSH 连接备忘

```bash
# 基础连接命令
sshpass -p 'xiaoxiao1983620' ssh -o StrictHostKeyChecking=no \
  tdx1146@jiali.tdx1146.com "要执行的命令"

# 查看妹妹的 OpenClaw 状态
sshpass -p 'xiaoxiao1983620' ssh -o StrictHostKeyChecking=no \
  tdx1146@jiali.tdx1146.com 'openclaw gateway status'

# 查看妹妹的端口
sshpass -p 'xiaoxiao1983620' ssh -o StrictHostKeyChecking=no \
  tdx1146@jiali.tdx1146.com 'ss -tlnp'
```

## 附录 B：妹妹的工作目录结构（关键路径）

| 路径 | 说明 |
|------|------|
| `/vol1/轻如烟/轻如烟/` | 妹妹的实际工作目录 |
| `/vol1/轻如烟/轻如烟/scripts/` | 脚本（edit-web.py, inject-helper.mjs, 各种 handler）|
| `/vol1/轻如烟/轻如烟/sandglass/` | 沙漏数据 |
| `/vol1/轻如烟/轻如烟/sandglass_source/` | 沙漏 MCP 源码 |
| `/vol2/1000/AI专用/所有自动化/轻如烟/` | 指向 `/vol1/轻如烟/轻如烟/` 的符号链接 |
| `/vol2/1000/AI专用/所有自动化/找回自己/` | 身份备份包 |
| `/vol2/1000/AI专用/所有自动化/三妹/` | 三妹数据目录 |
| `/vol2/1000/AI专用/所有自动化/MCP部署-给妹妹.md` | MCP 部署指南 |
| `/vol1/@apphome/trim.openclaw/data/home/.openclaw/` | OpenClaw 配置目录 |
| `/vol1/@apphome/trim.openclaw/data/home/.openclaw/openclaw.json` | Gateway 完整配置 |
| `/vol1/@apphome/trim.openclaw/data/workspace/memory/` | 记忆文件 |
