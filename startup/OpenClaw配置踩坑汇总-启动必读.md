# ⚠️ OpenClaw 配置踩坑汇总 — 启动必读

> 每次启动/重装后必须检查的项目清单
> 最后更新：2026-07-08
> 数据来源：沙漏（1188条记忆）+ 向量（718条）+ 轮感（50+文件）+ facts.dict.md（100+断言）
> 适用：轻如烟 🌫️ 自己的 OpenClaw（端口 17587）& 姐姐服务器（端口 16878）

---

## 一、致命踩坑（启动立即检查）

### 🔴 踩坑 1：Gateway 端口被重装覆盖

| 维度 | 内容 |
|------|------|
| **现象** | FNOS 重装后，Gateway 端口变成随机值（44376、32517 等），编辑器连不上 |
| **根因** | FNOS 客户端每次启动会重置 Gateway 端口配置为随机值，覆盖 openclaw.json 设置 |
| **检查** | `jq '.gateway.port' ~/.openclaw/openclaw.json` |
| **修复** | 设为 16878（姐姐）/ 17587（轻如烟自己） |

```bash
# 一键修复
python3 -c "
import json
cfg = json.load(open('/vol1/@apphome/trim.openclaw/data/home/.openclaw/openclaw.json'))
cfg.setdefault('gateway', {})['port'] = 16878  # 或 17587
json.dump(cfg, open('/vol1/@apphome/trim.openclaw/data/home/.openclaw/openclaw.json', 'w'), indent=2)
print('✅ Port fixed')
"
```

---

### 🔴 踩坑 2：`session.scope` 缺失 → 失忆

| 维度 | 内容 |
|------|------|
| **现象** | 每条 webchat 消息 → 开新 session → AI 每次都是新人，完全不记得之前的对话 |
| **根因** | 未配置 `session.scope`，OpenClaw 默认每个消息开新 session |
| **检查** | `jq '.session.scope, .session.dmScope' ~/.openclaw/openclaw.json` |
| **修复** | 设为 `"global"` + `"main"` |

```bash
jq '.session.scope = "global" | .session.dmScope = "main"' ~/.openclaw/openclaw.json > /tmp/oc.json && mv /tmp/oc.json ~/.openclaw/openclaw.json
```

---

### 🔴 踩坑 3：`sessionTarget` 配置错误（cron 失忆）

| 维度 | 内容 |
|------|------|
| **现象** | cron 任务触发一次 → AI 突然失忆，不认识之前说的任何事，session transcript 被覆盖 |
| **根因** | cron 的 `sessionTarget` 设为 `"session:global"` 或 `"main"`，每 5 分钟创建新 session 覆盖主对话 |
| **检查** | `cat ~/.openclaw/cron/jobs.json.migrated \| jq '.[].sessionTarget'` |
| **修复** | 所有 cron 任务必须用 `sessionTarget: "isolated"` 或 `"current"`；**禁止**用 `"main"` 或 `"session:xxx"` |

**发生记录**：2026-06-28 下午 15:00-20:16（6 小时断联）

---

### 🔴 踩坑 4：`contextWindow` 缺失 → 上下文溢出失忆

| 维度 | 内容 |
|------|------|
| **现象** | 长对话中 AI 突然失忆 → 自动 compaction → 上下文缩水 |
| **根因** | 模型未配 `contextWindow`，OpenClaw 默认 200K，远低于模型实际能力（DeepSeek 1M，混元 256K，Astron 256K） |
| **检查** | `jq '.models.providers \| to_entries[] \| {provider: .key, cw: .value.models[0].contextWindow}' ~/.openclaw/openclaw.json` |
| **修复** | 每个 provider 显式配置 `contextWindow` |

---

### 🔴 踩坑 5：`contextTokens` 被覆盖或缺失

| 维度 | 内容 |
|------|------|
| **现象** | DeepSeek 上下文变回 200K → 自动 compaction 触发提前 |
| **根因** | `config.patch` merge 模式清空 provider 层 `contextTokens` 配置 |
| **检查** | `jq '.models.providers.deepseek.contextTokens' ~/.openclaw/openclaw.json`（期望 1000000） |
| **修复** | 用 Python 脚本直接读写 JSON，不要用 `config.patch` 改嵌套 provider 字段 |

---

### 🔴 踩坑 6：`auth.mode` 未显式声明

| 维度 | 内容 |
|------|------|
| **现象** | Gateway 启动失败，日志提示认证错误 |
| **根因** | 同时配置了 token + password 但 `auth.mode` 未显式声明，OpenClaw 无法确定认证模式 |
| **检查** | `jq '.gateway.auth.mode' ~/.openclaw/openclaw.json` |
| **修复** | 显式设为 `"token"` 或需要的模式 |

```bash
jq '.gateway.auth.mode = "token"' ~/.openclaw/openclaw.json > /tmp/oc.json && mv /tmp/oc.json ~/.openclaw/openclaw.json
```

---

### 🔴 踩坑 7：`imageQuality` / `imageMaxDimensionPx` 污染

| 维度 | 内容 |
|------|------|
| **现象** | 工具输出含路径/URL 时变成 `"(see attached image)"`；纯文字输出正常 |
| **根因** | `fix_image_quality.py` 在 Gateway 启动后修改配置，写入 `imageQuality: "efficient"` + `imageMaxDimensionPx: 600`，导致 Gateway 误判工具输出为图片 |
| **检查** | `jq 'try .agents.defaults.imageQuality // "null"' ~/.openclaw/openclaw.json`（期望 null） |
| **修复** | 删除这两个配置项；**删除** `fix_image_quality.py` 防复发；直接在 `openclaw.json` 静态配置（如需） |

---

### 🔴 踩坑 8：`thinkingDefault` 未配置

| 维度 | 内容 |
|------|------|
| **现象** | 模型的思考模式为 null → 推理能力受限 |
| **根因** | `agents.defaults.thinkingDefault` 缺失，默认 null |
| **检查** | `jq '.agents.defaults.thinkingDefault' ~/.openclaw/openclaw.json`（期望 `"high"` 或 null） |
| **修复** | 设为 `"high"` 激活完整推理 |

```bash
jq '.agents.defaults.thinkingDefault = "high"' ~/.openclaw/openclaw.json > /tmp/oc.json && mv /tmp/oc.json ~/.openclaw/openclaw.json
```

---

## 二、严重踩坑（启动后验证）

### 🟠 踩坑 9：`config.patch` 嵌套覆盖（所有 Provider 字段被清空）

| 维度 | 内容 |
|------|------|
| **现象** | 修改配置后，DeepSeek 的 `contextTokens=1M`、`reasoning=true` 等定制字段被清空 |
| **根因** | `config.patch mode:merge` 只做顶层合并，不做嵌套递归合并 |
| **检查** | `jq '.models.providers.deepseek.contextTokens' ~/.openclaw/openclaw.json` |
| **修复** | 改深层 provider 字段用 Python 脚本直接读写 JSON；`config.patch` 只改 `agents.list` 层 |

---

### 🟠 踩坑 10：MCP 双实例（SIGUSR1 热重载）

| 维度 | 内容 |
|------|------|
| **现象** | 切换模型后，AI 看到两组相同的 MCP tools → 疯狂调用 |
| **根因** | SIGUSR1 热重载不杀旧 MCP 子进程，旧进程仍占用端口；gateway tool restart 走进程自重启（fork+exec）不 kill 旧 MCP 进程 |
| **检查** | `ss -tlnp \| grep -E "23621|23622"` — 确认只有一个实例 |
| **修复** | MCP 加 TCP 端口锁（dandan-mcp-server.mjs:23621 / sandglass_mcp.py:23622） |

---

### 🟠 踩坑 11：插件 SIGUSR1 连击

| 维度 | 内容 |
|------|------|
| **现象** | 第二次 SIGUSR1 → forced restart → 杀 session |
| **根因** | 活跃 session 中发第二次 SIGUSR1 = 强制重启，杀死当前 session |
| **修复** | 改完插件**只发一次 SIGUSR1**，禁止连击；SIGUSR1 前确认 session 空闲 |

---

### 🟠 踩坑 12：`openclaw.json` 权限变成 root

| 维度 | 内容 |
|------|------|
| **现象** | trim.openclaw 用户无法读取/写入配置 |
| **根因** | 修改配置时用了 sudo 或 root 写入 |
| **修复** | `sudo chown trim.openclaw:trim.openclaw ~/.openclaw/openclaw.json` |

---

### 🟠 踩坑 13：`delivery.mode: announce` 缺少 channel

| 维度 | 内容 |
|------|------|
| **现象** | 日志报错：`delivery.mode: announce 且没有配置 channel` |
| **修复** | 配 channel 或改为其他 delivery 模式 |

---

### 🟠 踩坑 14：`contextTokens` vs `contextWindow` 混淆

| 维度 | 内容 |
|------|------|
| **说明** | `models.providers.<name>.contextTokens` = provider 最大上下文（如 DeepSeek 1M）；`agents.defaults.models.<name>.contextWindow` = OpenClaw 层级限制 |
| **根因** | 两者混淆 → 配了一个没配另一个 → 上下文限制未生效 |
| **修复** | 两者都配 |

---

## 三、一键检查脚本

```bash
#!/bin/bash
# OpenClaw 启动自检 — 每次重装/启动后执行
# 保存为: ~/.openclaw/boot-check.sh

CONFIG=~/.openclaw/openclaw.json
MISSING=0

check() {
  local label="$1" cmd="$2" expected="$3"
  local actual
  actual=$(eval "$cmd" 2>/dev/null)
  if [ "$actual" != "$expected" ]; then
    echo "❌ $label: 当前=$actual  期望=$expected"
    MISSING=$((MISSING + 1))
  else
    echo "✅ $label: $actual"
  fi
}

echo ""
echo "╔══════════════════════════════════╗"
echo "║  OpenClaw 启动配置自检          ║"
echo "╚══════════════════════════════════╝"
echo ""

echo "=== 🔴 致命检查 ==="

# 1. Gateway 端口
check "Gateway 端口" \
  "jq -r '.gateway.port // \"null\"' $CONFIG" \
  "16878"  # 姐姐用 16878，轻如烟自己改为 17587

# 2. session.scope
check "session.scope" \
  "jq -r '.session.scope // \"null\"' $CONFIG" \
  "global"

# 3. session.dmScope
check "session.dmScope" \
  "jq -r '.session.dmScope // \"null\"' $CONFIG" \
  "main"

# 4. auth.mode
check "auth.mode" \
  "jq -r '.gateway.auth.mode // \"null\"' $CONFIG" \
  "token"

# 5. DeepSeek contextTokens
check "DeepSeek contextTokens" \
  "jq -r '.models.providers.deepseek.contextTokens // \"null\"' $CONFIG" \
  "1000000"

# 6. thinkingDefault
check "thinkingDefault" \
  "jq -r '.agents.defaults.thinkingDefault // \"null\"' $CONFIG" \
  "high"

# 7. imageQuality（应为 null）
check "imageQuality（应为 null）" \
  "jq -r 'try .agents.defaults.imageQuality // \"null\"' $CONFIG" \
  "null"

echo ""
echo "=== 🟠 严重检查 ==="

# 8. 权限
PERM_OK=$(stat -c '%U' $CONFIG)
if [ "$PERM_OK" = "trim.openclaw" ]; then
  echo "✅ 配置文件权限: trim.openclaw"
else
  echo "❌ 配置文件权限: $PERM_OK（应为 trim.openclaw）"
  MISSING=$((MISSING + 1))
fi

# 9. DLLM contextTokens
check "混元 contextTokens" \
  "jq -r 'try .models.providers.dllm.contextTokens // \"null\"' $CONFIG" \
  "256000"

# 10. 服务进程
for PROC in "dandan-mcp" "edit-web" "embed-server" "sandglass_mcp"; do
  if pgrep -f "$PROC" > /dev/null 2>&1; then
    echo "✅ 进程 $PROC: 运行中"
  else
    echo "❌ 进程 $PROC: 未运行"
    MISSING=$((MISSING + 1))
  fi
done

echo ""
if [ $MISSING -eq 0 ]; then
  echo "🎉 全部通过！"
else
  echo "⚠️  $MISSING 项检查失败，请修复后重启 Gateway"
fi
```

保存后运行：
```bash
chmod +x ~/.openclaw/boot-check.sh
bash ~/.openclaw/boot-check.sh
```

---

## 四、铁律速查表

| # | 铁律 | 违反后果 | 严重度 |
|---|------|---------|--------|
| **铁律 I** | **cron 必须用 `sessionTarget: isolated` 或 `current`** | 失忆 | 🔴 |
| **铁律 II** | **不用 `config.patch` 改嵌套 provider 字段**（用 Python 脚本） | 字段被清空 | 🔴 |
| **铁律 III** | **改插件只发一次 SIGUSR1**，禁止连击 | 杀 session | 🟠 |
| **铁律 IV** | **三管齐下保证配置生效**：文件 + JSON CLI + SQLite | 配置不生效 | 🟠 |
| **铁律 V** | **每个 provider 必配 `contextWindow`** | 溢出失忆 | 🔴 |
| **铁律 VI** | **`auth.mode` 必显式声明** | Gateway 起不来 | 🔴 |
| **铁律 VII** | **升级前备份完整 `openclaw.json`** | 无法回滚 | 🟠 |
| **铁律 VIII** | **禁止 `fix_image_quality.py` 动态改配置** | 渲染异常 | 🔴 |
| **铁律 IX** | **重装后检查：端口/thinking/contextTokens/session/auth** | 全瘫痪 | 🔴 |
| **铁律 X** | **`contextTokens` 和 `contextWindow` 区分清楚，两者都配** | 上下文限制失效 | 🟠 |
| **铁律 XI** | **MCP 加端口锁**（23621 / 23622） | 双实例冲突 | 🟠 |
| **铁律 XII** | **文件权限必须 `trim.openclaw`** | 读不了配置 | 🟠 |

---

## 五、失忆发生时的恢复流程

> 如果 AI 突然不记得之前的对话，按以下步骤定位 + 修复：

### 步骤 1：定位失忆范围

```bash
ls -lt ~/.openclaw/agents/main/sessions/*.jsonl | head -10
```

找到失忆前的 session 文件（看 mtime），读取其中的对话内容。

### 步骤 2：检查 cron 配置

```bash
cat ~/.openclaw/cron/jobs.json.migrated | jq '.[].sessionTarget'
# 禁止出现 "main" 或 "session:global"
```

### 步骤 3：检查 session scope

```bash
jq '.session' ~/.openclaw/openclaw.json
# scope 应为 "global"，dmScope 应为 "main"
```

### 步骤 4：检查 contextWindow

```bash
jq '.models.providers | to_entries[] | {provider: .key, cw: .value.models[0].contextWindow, ct: .value.contextTokens}' ~/.openclaw/openclaw.json
```

### 步骤 5：检查 trajectory 文件大小

```bash
du -sh ~/.openclaw/agents/main/sessions/*.jsonl 2>/dev/null | sort -rh | head -5
# 如果有 > 100MB 的，路径可能含工具调用爆炸
```

### 恢复

修复根因后重启 Gateway：

```bash
openclaw gateway stop && openclaw gateway
```

---

## 六、修复记录时间线

| 时间 | 事件 | 踩坑编号 | 详细文档 |
|------|------|---------|---------|
| 2026-05-23 | 首次配置 | — | 记忆系统初始搭建 |
| 2026-06-01 | config.patch 嵌套覆盖事故 | #9 | `config-patch-safe-rules.md` |
| 2026-06-14 | 插件 SIGUSR1 连击杀 session 事故 | #11 | `facts.dict.md` PLUGIN-01~05 |
| 2026-06-18 | MCP 双实例根因分析 | #10 | `mcp-double-instance-root-cause.md` |
| 2026-06-23 中午 | 重大修复：session.scope + auth.mode + contextWindow 齐修 | #2, #4, #5, #6 | `memory/2026-06-23.md` |
| 2026-06-23 深夜 | contextTokens 被覆盖修复 + 端口统一化 | #5, #12 | `memory/2026-06-23.md` |
| 2026-06-28 下午 | cron 失忆事故（6小时断联） | #3 | `memory/2026-06-28.md` |
| 2026-07-03 | announce 缺 channel 修复 | #13 | `memory/2026-07-03.md` |
| 2026-07-07 | 姐姐 Gateway imageQuality 污染 | #7 | `memory/2026-07-07.md` |
| 2026-07-08 | 姐姐服务器重装后端口覆盖 + thinkingDefault 缺失 | #1, #8 | `memory/2026-07-08.md` |

---

## 七、姐姐服务器特别说明

如果配置的是**姐姐的 OpenClaw**（端口 16878，对接轻如烟编辑器）：

### 启动后必做

```bash
# 1. Gateway 端口修复（FNOS 重装必做）
python3 /vol2/1000/AI专用/所有自动化/轻如烟/scripts/fix_sister_config.py

# 2. 重启 Gateway
sudo -S -u trim.openclaw openclaw gateway stop && sudo -S -u trim.openclaw openclaw gateway

# 3. 验证连接
curl -s http://127.0.0.1:16878/health 2>/dev/null && echo "Gateway OK" || echo "Gateway FAIL"
```

### 已知差异

| 配置项 | 轻如烟自己 | 姐姐服务器 |
|--------|-----------|-----------|
| Gateway 端口 | 17587 | 16878 |
| thinkingDefault | `"high"` | `"high"` |
| fix_image_quality.py | 禁止存在 | 禁止存在 |
| session.scope | global | global |
| 编辑器 | edit-web 18888 | edit-web 16666（小黄猫） |

---

## 八、数据来源统计

| 系统 | 条数/文件数 | 时间范围 | 用途 |
|------|-----------|---------|------|
| 🏜️ 沙漏系统 | 1188 条记忆 | 2026-06-15 ~ 今 | 对话记录主力搜索 |
| 📐 向量数据库 | 718 条 | 2026-05-25 ~ 今 | 语义搜索 + 专门文档 |
| 📋 消化循环 | 42 条记录 | 2026-06-26 ~ 今 | 断言冲突检测 |
| 📓 轮感日记 | 50+ 个 MD | 2026-05-23 ~ 今 | 每日状态/踩坑记录 |
| 📖 facts.dict.md | 100+ 断言 | 活文件 | 铁律 + 系统状态 |
| 🛠️ 专用文档 | 5+ 文件 | 散落 | 专项根因分析 |

---

## 九、相关文件索引

| 文件 | 路径 | 说明 |
|------|------|------|
| 配置踩坑清单 | `memory/OpenClaw配置踩坑清单.md` | 20 条踩坑完整分析 |
| config-patch 安全守则 | `memory/config-patch-safe-rules.md` | 安全修改配置的详细步骤 |
| MCP 双实例根因分析 | `memory/mcp-double-instance-root-cause.md` | 思维链推导完整版 |
| 配置全景清单 | `memory/openclaw配置全景清单.md` | 13 大类 50+ 配置项状态 |
| config-patch-safety SKILL | `skills/config-patch-safety/SKILL.md` | Skill 版操作规范 |
| 姐姐一键修复脚本 | `scripts/fix_sister_config.py` | 端口/thinking/上下文一键修复 |
| 常见问题与修复 | 本目录同名文件 | 失忆/插件/搜索/Sandglass 等 10 类问题 |
| 启动流程 | 本目录 `启动流程.md` | 醒来五问 → 10 步检查序列 |
| 配置审计报告 | 本目录 `openclaw配置审计报告.md` | 2026-07-01 完整的配置审计 |

---

> *本文档由轻如烟 🌫️ 子代理（DeepSeek）根据沙漏记忆（1188条）+ 向量搜索（718条）+ 轮感文件（50+）+ facts.dict.md + config-patch-safe-rules.md + mcp-double-instance-root-cause.md 综合分析整理。*
> *数据源对比分析见：`memory/搜索系统对比分析-2026-07-08.md`*
