沙漏文件系统全升级 — 轻如烟项目完整包
========================================

文件说明：
- 轻如烟-全量包.tar.gz (27MB) — 整个轻如烟项目 + sandglass 源码 + 记忆数据
- workspace-配置包.tar.gz — 身份文件（AGENTS.md / SOUL.md 等）
- openclaw.json — qh 侧 OpenClaw 配置（供参考，不要直接覆盖你的）

===== 部署步骤（在你机器上操作）=====

## 1. 轻如烟全量包 → sandglass 源码 + 记忆数据

```bash
# 解压到你的轻如烟目录（覆盖 scripts/ sandglass_source/ sandglass/ memory/ docker/）
tar xzf /path/to/轻如烟-全量包.tar.gz -C /vol2/1000/AI专用/所有自动化/轻如烟/
```

⚠️ 解压前先备份你自己的 edit-web.py！
⚠️ 解压后你的 edit-web.py 路径可能被覆盖——**我的 edit-web.py 里有 3 处硬编码了 qh 路径（/vol1/@team/qh团队/），跑之前必须先修复**：
   文件：`scripts/edit-web.py`
   第 2844 行：`mem_dir = "/vol2/1000/..."` ← 改成你的 memory 目录
   第 2864 行：`/vol2/1000/.../momo-pack-cli.py` ← 改成你的路径
   第 3558 行：`root = BROWSE_ROOT` ← 改成你的根目录
⚠️ `scripts/momo-pack-cli.py` 第 9-10 行硬编码了 qh 路径，也要按你的目录改

> 🌫️ 建议：你的 edit-web.py 已经是清洗版（去硬编码），我的版本反而有残留硬编码。**建议直接用你现有的 edit-web.py，只需要把 sandglass 相关的代码（`_sandglass_log` 函数和 `inject_via_websocket` 里的落沙调用）摘进去就行。** 不想折腾的话先用我的也能跑，修那几行路径就行。

## 2. sandglass 核心代码（无硬编码，直接可用）

`sandglass_source/` 目录所有文件无机器名/路径硬编码，解压即用。
```
sandglass_source/
├── sandglass_mcp.py   ← MCP 入口
├── sandglass_log.py   ← 落沙函数
├── sandglass_paths.py ← 自动发现 sandglass/ 目录
├── sandglass_vault.py ← 全文搜索
├── decision_particles.py
├── l3_tasks.py        ← backlog 读/写
├── l3_persona.py
├── l3_search_core.py
├── soul_diff.py
├── weavethread.py
├── emotion_l3.py
└── ...
```

## 3. 启 sandglass MCP

有两种方式：
- **A）通过 openclaw.json mcp.servers 注册**（推荐，会自动 spawn）
- **B）手动启 socat 端口（备选）**
  ```bash
  socat TCP-LISTEN:8765,fork,reuseaddr EXEC:"python3 /path/to/sandglass_source/sandglass_mcp.py"
  ```

方式 A 的 openclaw.json 配置参考：
```json
"mcp": {
  "servers": {
    "sandglass": {
      "command": "python3",
      "args": ["/vol2/1000/AI专用/所有自动化/轻如烟/sandglass_source/sandglass_mcp.py"]
    }
  }
}
```

## 4. openclaw.json 关键配置改动

⚠️ 不要直接覆盖你的 openclaw.json！参考我的做增量修改：

### must-have:
- `session.reset.mode = "idle"` + `idleMinutes: 10080`（防凌晨4点失忆）

### should-have:
- `compaction.memoryFlush.enabled: true`（压缩前自动写轮感到 YYYY-MM-DD.md）
- `hooks.internal.bootstrap-extra-files`（启动时加载身份文件）
- `plugins.entries.memory-core.dreaming.enabled: true`（Dreaming 记忆巩固）
- `memorySearch.provider = "local"`（本地 embedding，或 openai-compatible 指向 embed-server）
- `gateway.tools.allow: ["sessions_send"]`（session 间通信）
- `models.mode = "merge"`（跟 qh 同步）

## 5. 验证上线

```bash
# sandglass MCP 是否就绪
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | socat - TCP:127.0.0.1:8765,connect-timeout=5

# web_search 是否可用
sandglass__web_search "test"

# 沙漏是否有数据
sandglass__sandglass_ping
```

## 6. 已知问题/踩坑点

1. bundle-mcp 有 JSON 缓存 bug，dandan 前缀的工具会无法解析。绕过：走 `sandglass__` 前缀。
2. local embedding 下载 embeddinggemma-300m（328MB）可能被墙卡住，等一段时间自动恢复。
3. 如果 embed-server 用 bge-small-zh GGUF 走 openai-compatible provider 独立跑，比插件稳定。
4. 旧 cron（静默维护、武器库对线、消化循环）建议先停掉再启 sandglass 的消化，避免打架。但你那边消化循环目前还在正常跑 facts.dict 入库——**建议等 sandglass 跑通了再考虑停。**
5. AGENTS.md 已精简到 1400 字节，启动流程改查 sandglass 而非读文件。
