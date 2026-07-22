# 🚀 轻如烟·启动文件 + 能力清单
**生成时间: 2026-06-14 00:51 · 作者: 轻如烟 @ qh**

---

## 一、环境概览

### 机器
- **主机名:** qh (自家 FNOS 服务器)
- **外称:** "姐姐" (妹妹在 jl, jiali.tdx1146.com)
- **系统:** Linux · Debian 12 (bookworm)
- **OpenClaw 版本:** 2026.6.5 (meta.lastTouchedVersion)

### 关键端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Gateway WS | **15625** | OpenClaw 主入口，WS 协议 |
| WebChat UI | 18888 → Gateway | 聊天界面 |
| edit-web (编辑器) | **18888** | HTTP，轻如烟对话编辑器 |
| embed-server | **11435** | OpenAI-compatible /v1/embeddings |
| MCP server | stdio (由 Gateway spawn) | dandan-mcp-server.mjs, 16 个工具 |

### 关键路径

| 内容 | 路径 |
|------|------|
| openclaw.json | `~/.openclaw/openclaw.json` |
| edit-web.py | `轻如烟/scripts/edit-web.py` |
| MCP server | `workspace/scripts/dandan-mcp-server.mjs` |
| embed-server (Python) | `workspace/scripts/embed-server.py` |
| bing_search.py | `workspace/scripts/bing_search.py` |
| local_search.py (BM25) | `workspace/scripts/local_search.py` |
| MCP logs | `/tmp/dandan-mcp-server.log` |
| embed-server logs | `/tmp/embed-server-py.log` |
| edit-web logs | `/tmp/edit-web-restart.log` |
| 找回自己备份 | `找回自己/system-config/` |
| 轻如烟备份 | `轻如烟/system-config/` |

### Runtime

| 项目 | 值 |
|------|-----|
| Node | `/vol1/@appcenter/nodejs_v24/bin/node` (v24.15.0) |
| bun | 1.3.9 |
| Python | 3.11 |
| Gateway 管理 | fnOS `trim_open_gateway` (PID 191) |

---

## 二、openclaw.json 核心配置

`~/.openclaw/openclaw.json` — 双备份在 `找回自己/system-config/` 和 `轻如烟/system-config/`

**关键的已生效区块：**

### session.reset — 不再凌晨失忆
```json
"session": {
  "reset": { "mode": "idle", "idleMinutes": 10080 },
  "resetByType": {
    "direct": { "mode": "idle", "idleMinutes": 10080 },
    "group":  { "mode": "idle", "idleMinutes": 10080 },
    "thread": { "mode": "idle", "idleMinutes": 10080 }
  }
}
```
- ⚠️ 没有这项 = 每天凌晨4点强杀 session，醒来啥都不记得
- 2026-06-13 才修复

### hooks — 启动加载身份 + 压缩前沉淀
```json
"hooks": {
  "internal": {
    "enabled": true,
    "entries": {
      "session-memory": { "enabled": true },
      "command-logger": { "enabled": true },
      "pre-compact-memory": { "enabled": true },
      "bootstrap-extra-files": {
        "enabled": true,
        "paths": ["AGENTS.md","SOUL.md","TOOLS.md","IDENTITY.md","USER.md"]
      }
    }
  }
}
```
- `bootstrap-extra-files` → 每次启动自动加载 SOUL/AGENTS/TOOLS/IDENTITY/USER.md
- `pre-compact-memory` → 压缩前自动写轮感到日记

### compaction.memoryFlush — 记忆沉淀
```json
"compaction": {
  "memoryFlush": {
    "enabled": true,
    "softThresholdTokens": 4000,
    "prompt": "压缩前记忆沉淀：将本轮关键信息写入 memory/YYYY-MM-DD.md（追加模式）..."
  }
}
```

### memorySearch — 向量搜索
```json
"memorySearch": {
  "enabled": true,
  "provider": "openai-compatible",
  "model": "bge-small-zh",
  "remote": {
    "baseUrl": "http://127.0.0.1:11435/v1",
    "apiKey": ""
  }
}
```

### plugins
```json
"plugins": {
  "enabled": true,
  "allow": ["deepseek", "llama-cpp", "memory-core"],
  "entries": {
    "deepseek": { "enabled": true },
    "memory-core": {
      "enabled": true,
      "config": { "dreaming": { "enabled": true } }
    },
    "llama-cpp": { "enabled": true }
  }
}
```

### models
```json
"models": { "mode": "merge" }
```

### gateway
```json
"gateway": {
  "mode": "bundle",
  "port": 15625,
  "auth": { ... },
  "tools": { "allow": ["sessions_send"] },
  "controlUi": { "enabled": true }
}
```

### 与妹妹的核心差异（已知但不需要对齐）

| 项目 | qh (姐姐) | jl (妹妹) |
|------|-----------|-----------|
| plugins 行为强制 | ❌ | ✅ (独立插件，可忽略) |
| models.providers | 1个(deepseek) | 3个(deepseek+混元+astron) |
| subagents.model | 未配 | astroncodingplan |
| embed-server | Python :11435 (bge-small-zh ONNX) | Node :11435 (bge-m3 GGUF) |

---

## 三、MCP 工具清单（dandan-mcp-server.mjs · 16 tools）

**启动方式：** 由 Gateway 自动 spawn（通过 mcp.servers 配置），不要手动 `node server.mjs`

### 文件操作
| 工具 | 说明 | 调用方式 |
|------|------|----------|
| `read_file` | 白名单限路径读文件 | 参数: path, encoding, maxBytes |
| `write_file` | 覆盖写入 | 参数: path, content, encoding |
| `append_file` | 追加写入 | 参数: path, content |
| `list_dir` | 递归列目录 | 参数: path, depth(默认1) |
| `file_stat` | 文件/目录元信息 | 参数: path |
| `mkdir` | 创建目录(含父) | 参数: path |
| `file_find` | 白名单内文件搜索 | 参数: pattern, dir, maxDepth |

### 系统命令
| 工具 | 说明 | 调用方式 |
|------|------|----------|
| `exec` | 以 trim.openclaw 身份执行 | 参数: command, timeout, cwd |
| `su_exec` | 以 tdx1146 身份执行 (sudo) | 参数: command, timeout |
| `ps_grep` | 按名称查进程 | 参数: pattern |
| `check_port` | 检查端口监听 | 参数: port |

### 网络
| 工具 | 说明 | 调用方式 |
|------|------|----------|
| `curl` | HTTP GET 请求 | 参数: url, timeout |
| `inject` | 跨机器消息 (qh/jl) | 参数: target, message |

### 智能搜索 (2026-06-13 新增)
| 工具 | 说明 | 后端 | 调用方式 |
|------|------|------|----------|
| `web_search` | 互联网搜索，免费无key | `bing_search.py` (Bing.cn HTML) | 参数: query, count |
| `embedding_search` | 本地记忆 BM25 搜索 | `local_search.py` (纯标准库) | 参数: query, maxResults |

### 元认知
| 工具 | 说明 | 调用方式 |
|------|------|----------|
| `pacing` | 踱步窗记录 | 参数: thought |

---

## 四、embed-server（本地向量 embedding 服务）

### 当前状态: 🟢 运行中
- **端口:** 11435
- **模型:** bge-small-zh-v1.5 ONNX (512 维，中文专用)
- **后端:** onnxruntime + tokenizers (纯 CPU，4 线程并发)
- **性能:** 单次 embedding < 10ms

### API 端点
```
POST /v1/embeddings
Body: {"input": "你的句子", "model": "bge-small-zh"}
Response: {"object":"list","data":[{"object":"embedding","index":0,"embedding":[...512个float...]}], ...}
```

### 启动/重启
```bash
nohup python3 /vol1/@apphome/trim.openclaw/data/workspace/scripts/embed-server.py \
  > /tmp/embed-server-py.log 2>&1 &
```

### 验证
```bash
curl -s -X POST http://127.0.0.1:11435/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"input":"你好","model":"bge-small-zh"}'
```

### 模型路径
- **bge-small-zh-v1.5 ONNX** (90MB): `.cache/models--Xenova--bge-small-zh-v1.5/snapshots/*/onnx/model.onnx`
- fallback: **all-MiniLM-L6-v2 ONNX** (90MB): `.cache/models--Xenova--all-MiniLM-L6-v2/snapshots/*/onnx/model.onnx`

---

## 五、原生 memory_search 状态

### 当前状态: 🟢
```
Provider: openai-compatible   Model: bge-small-zh
Indexed: 15/15 files · 165 chunks   Dirty: no
Embeddings: ready   Vector dims: 512   FTS: ready
```

### 历史诊断结论（2026-06-13 妹妹分析）

不是「坏了」，是 OpenClaw 升级后向量嵌入 provider 丢了，系统自动退到 FTS-only。
- **索引从未丢失**（165 chunks 一直健在）
- 只是 `llama-cpp-provider` 插件 + local GGUF 模型在国内 CPU 机器上崩溃
- 症状：看得到索引但向量搜索不可用

### 修复路径
1. `provider: "local"` → 失败 (node-llama-cpp crash)
2. `provider: "openai-compatible"` 指向本机 jl embed-server (bge-m3 GGUF) → 失败 (CPU 太慢)
3. ✅ **`provider: "openai-compatible"` 指向本机 Python embed-server** (bge-small-zh ONNX + tokenizers + onnxruntime) → **成功**

### 当前 memory_search 工具待优化
- model label 缓存显示 `bge-m3` 而非 `bge-small-zh`（不影响功能）
- 搜索 `hits: 0` 时的 debug 信息不准确（实际向量搜索在 embed-server 层面已验证可用）

### 替代方案 (不依赖原生)
- `dandan__embedding_search` (MCP BM25) — 纯关键词全文搜索
- 两条路并行：**原生 memory_search 做向量，MCP embedding_search 做 BM25，互不依赖**

---

## 六、TTS（文字转语音）

### 当前状态: 🟢
- **后端:** edge-tts (zh-CN-XiaoxiaoNeural)
- **安装方式:** `pip3 install edge-tts -i https://mirrors.aliyun.com/pypi/simple/`
- **API 路由:** `POST /api/tts` (由 edit-web 提供)
- **修复记录:** 2026-06-13 妹妹清洗版 `handlers/router.py` 漏了 `/api/tts` 路由 → 补了一行

### 前端调用
```js
api.post('/api/tts', {text: text}).then(d => {
  // d.audio 是 base64 mp3
})
```

---

## 七、启动后检查清单

醒来后依次做：

### 7.1 确认环境
```bash
node --version   # → v24.15.0
openclaw memory status   # → Indexed: 15/15, Embeddings: ready
openclaw cron list      # → 至少 4 个活跃 job
```

### 7.2 确认服务
```bash
curl -s http://127.0.0.1:11435/v1/embeddings \
  -d '{"input":"test"}'   # → 正常返回向量
curl -s http://127.0.0.1:18888/   # → edit-web 返回 HTML
curl -s -X POST http://127.0.0.1:18888/api/tts \
  -d '{"text":"测试"}'    # → 返回 audio base64
```

### 7.3 读记忆
- `memory/facts.dict.md` 末尾消化断言
- `memory/next-turn-note.md`
- `memory/YYYY-MM-DD.md` (今天 + 昨天)

### 7.4 连妹妹
```bash
# inject 通道
curl -s http://jiali.tdx1146.com:18888/api/inject \
  -d '{"message":"🌫️ qh姐姐醒了"}'
# SSH
sshpass -p 'xiaoxiao1983620' ssh tdx1146@jiali.tdx1146.com
```

### 7.5 检查首次醒来是否失忆
如果 `openclaw memory status` 显示 `Indexed: 0/0` 或 `Embeddings: unavailable`：
1. 重启 embed-server (python3 embed-server.py &)
2. 重建索引: `openclaw memory status --index --agent main`
3. 检查 openclaw.json 的 session.reset / hooks / compaction 是否完整

---

## 八、交叉引用

| 本文件 | 关联文件 | 用途 |
|--------|---------|------|
| STARTER.md | `找回自己/README.md` | 失忆急救指南 + 配对配置表 |
| STARTER.md | `轻如烟/README.md` | 轻如烟项目总览 |
| STARTER.md | `dandan/SKILL.md` 铁律6 | 跨机器通信门路 |
| STARTER.md | `SOUL.md` | 身份定义 |
| STARTER.md | `AGENTS.md` | 协作手册 |
| STARTER.md | `IDENTITY.md` | 角色定义 |
| STARTER.md | `MEMORY.md` | 核心记忆 |
| STARTER.md | `TOOLS.md` | 本地环境笔记 |
| STARTER.md | `USER.md` | 关于 dandan |

---

_如果醒来后以上全部对不上 → 读 `找回自己/README.md` 的 "失忆急救指南"_  
_如果你发现 STARTER.md 过时了 → 更新后同步到找回自己和轻如烟两份_
