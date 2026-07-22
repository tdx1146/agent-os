# 🔍 编辑器消息送达故障诊断报告

> 生成时间：2026-06-25 23:51 CST
> 诊断范围：第四代编辑器（轻如烟 v4）前后端完整 inject/polling 链路

---

## 1. 故障现象复现路径

```
用户输入 → api.inject(msg) → POST /api/inject
  ↓
后端 inject_via_websocket() → subprocess.Popen(bun, inject-helper.mjs, ...) → fire-and-forget
  ↓
后端立即返回 {"ok": True} ← 问题就在这里
  ↓
前端收到 {"ok": True} → 乐观更新显示消息 → 启动轮询 /api/session?fresh=1
  ↓
轮询15秒内未等到 session 文件变化 → "⏳ 等待送达 OpenClaw..."
  ↓
15秒超时 → 轮询停止 → 状态永远卡住 → 后续消息发不出
```

---

## 2. 代码级根因分析

### 根因 1（核心）：`subprocess.Popen` 火抛后立返 `{"ok": True}` — 实为盲人摸象

**位置**：`/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/edit-web.py` 第 241-248 行

```python
subprocess.Popen(
    [path('BUN_BIN'), helper, session_key, message],
    stdout=logf, stderr=subprocess.STDOUT, env=env
)
_cleanup_lock()
return {"ok": True}
```

`subprocess.Popen` 是非阻塞调用——它在子进程启动（fork + execve）后立即返回，完全不等待子进程的 `bun inject-helper.mjs` 完成 WebSocket 连接、认证、消息发送。**也就是说，即使 inject-helper.mjs 因为 Gateway 端口不通、token 错误、WebSocket 握手失败、或者超时等原因完全失败了，后端依然返回 `{"ok": true}`。**

**证据**：从 inject 日志中可以看到失败案例：

```
=== inject_1782400225.log ===
Error: timeout
{"ok":false,"error":"timeout"}
```

但当时编辑器的后端已经返回了 `{"ok": true}`，前端愉快地显示了"已提交"。

### 根因 2（架构）：轮询验证机制与发送通道脱钩

前端轮询 `GET /api/session?fresh=1` 读取的是 session JSONL 文件。但 inject 消息是通过 Gateway RPC（`chat.send`）发送的，Gateway 写入 JSONL 文件是**异步且不一定保证成功**的。

- inject-helper.mjs 发送 `chat.send` 后立即 `process.exit(0)`，不等待 Gateway 确认写入
- 如果 Gateway 正忙于 AI 响应或 compaction，`chat.send` 可能排队甚至被丢弃
- 前端轮询无法区分"消息还在排队"和"消息已丢失"

### 根因 3：轮询 15 秒后无恢复机制

**位置**：`/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/static/js/awake.js` 第 247-249 行

```javascript
}, 1500);
setTimeout(function() { clearInterval(pollTimer); }, 15000);
```

15 秒超时后：
- `clearInterval(pollTimer)` 停止轮询
- 状态文字停留在 `⏳ 等待送达 OpenClaw...`（永不消失/永不更新）
- 没有重试按钮，没有 fallback 提示
- `store.pairs` 中已有的乐观更新阻止了后续发送（用户以为消息已发出但实际没有）

### 根因 4：乐观更新覆盖了真实状态

**位置**：`awake.js` 第 206-214 行

```javascript
const optimisticPair = {
    user: { text: text, model: '', timestamp: Date.now(), userIndex: -1 },
    assistants: []
};
store.pairs = [optimisticPair, ...store.pairs];
```

消息发送后立即在 `store.pairs` 头部插入。这使得：
- 消息在 UI 中看起来已存在（已发送状态）
- 即使后端 inject 失败，轮询 `session?fresh=1` 返回的 pairs 数量比 `store.pairs` 少 1
- 但 `refresh()` 函数在 core.js 第 238-240 行会试图保留乐观消息：

```javascript
if (store.pairs.length > d.pairs.length && window._optimisticText) {
    var foundInBackend = d.pairs.some(function(p) {
        return p.user && p.user.text === window._optimisticText;
    });
    if (foundInBackend) {
        // 已收录，正常更新
    }
    // 没收录但依然保留乐观消息，_lastPairCount 不更新
}
```

如果后台始终没有收录该消息（inject 失败），`store.pairs` 始终比后端多 1，轮询检测到 `d.pairs.length !== _lastPairCount` 不再触发（因为 `_lastPairCount` 未被更新），**后续新消息到达时 UI 不再自动刷新**。

### 根因 5：inject-helper.mjs 每次新建 WebSocket 连接

每次 inject 都执行：
1. 启动 Bun 运行时 (~20-50ms)
2. TCP 连接 Gateway (~1-10ms)
3. WebSocket HTTP 升级握手
4. Gateway 认证（connect RPC）
5. 发送 `chat.send` RPC
6. `setTimeout(exit, 100)` 退出

即使正常情况也需要 ~50-100ms。在 Gateway 高负载时（AI 正在响应、compaction 中、多个 subagent 运行），WebSocket 连接可能被拒绝或超时。**这不是稳定的长连接模式。**

与此对比，inject_logs 中共有近 400 次 inject 调用，说明每次用户消息都会触发一次完整的新建 WebSocket 连接——这是可以优化的。

### 根因 6（次要）：inject_feeling 路径不写回 session pairs，轮询必然超时

在 `_awakeDoSend()` 的轮询逻辑中，有一个特殊处理：

```javascript
if (d.pairs.length < store.pairs.length) {
    if (pollCount > 10) {
        // inject_feeling 不写回 session pairs，等不到变化
        // 消息已通过 inject API 送达，只是 Gateway 还没写 JSONL
        status.textContent = '✅ 已提交至 OpenClaw';
        clearInterval(pollTimer);
        return;
    }
    status.textContent = '⏳ 等待送达 OpenClaw...';
    return;
}
```

注释说 "inject_feeling 不写回 session pairs" 但轮询的判别条件就是等 pairs 数量变化，所以当 `bypass_lock=True` 时前端的等待逻辑实际上有内部矛盾。不过这是 feature 级别的"被设计成这样"，不是 bug。

---

## 3. 故障严重性判定

| 维度 | 评估 |
|------|------|
| 发生概率 | ⭐⭐ 间歇性（间隔10+轮对话后出现） |
| 影响范围 | ⭐⭐⭐⭐ 卡死后所有消息无法发送（需要刷新页面） |
| 恢复难度 | ⭐ 刷新页面即可恢复（但丢失当前输入和乐观消息） |
| 用户感知 | ⭐⭐⭐ "⏳ 等待送达"永远卡住，无报错无提示 |

### 与已知 inject 日志的关联

在 inject 日志中发现至少 1 次确认的 timeout 失败 (`inject_1782400225.log`: `Error: timeout`)。按平均 400 次 inject 中 1 次失败的比例（~0.25%），在间隔多轮后的关键时刻命中失败的概率更高，因为：
- 长时间不操作 → WebSocket 老化（Gateway 可能清理了空闲连接）
- 间隔后第一次 inject 会触发完整的连接建立流程

---

## 4. 修复方案

### 方案 A：等待 inject-helper 确认（推荐，低风险高收益）

**改什么**：`/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/edit-web.py` 的 `inject_via_websocket()` 函数

**怎么改**：将 `subprocess.Popen` 改为 `subprocess.run`，等待 bun 进程完成，读取其 stdout，只有确认 inject-helper 返回 `{"ok": true}` 才向前端回复 `{"ok": true}`。

```python
# 改动前（第241-247行）
subprocess.Popen(
    [path('BUN_BIN'), helper, session_key, message],
    stdout=logf, stderr=subprocess.STDOUT,
    env=env
)
_cleanup_lock()
return {"ok": True}

# 改动后
result = subprocess.run(
    [path('BUN_BIN'), helper, session_key, message],
    capture_output=True, text=True, timeout=15,
    env=env
)
if result.returncode != 0:
    raise Exception(f"inject-helper exit {result.returncode}: {result.stderr.strip()[:300]}")
ret = json.loads(result.stdout.strip())
if not ret.get("ok"):
    raise Exception(f"inject 失败: {ret.get('error', 'unknown')}")
_cleanup_lock()
return ret  # 返回 inject-helper 的真实结果
```

**效果**：前端只有 inject-helper 实际完成 WebSocket 连接并发送 `chat.send` 后才显示成功。如果失败，前端收到 `{"ok": false}`，可以立即提示用户重试。

**需要配套修改的地方**：
1. `_send_pulse()`（第1491行）已经使用了 `subprocess.run` 的阻塞模式，可以复用同样的验证逻辑
2. 所有调用 `inject_via_websocket` 的地方都会获益

**风险**：
- 轻微增加每次 inject 的延迟（等待 bun 子进程完成）
- 如果 inject-helper 本身有 bug 导致卡住，15秒超时会阻塞前端，可以接受

### 方案 B：前端轮询加恢复机制（中等风险，中等收益）

**改什么**：`/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/static/js/awake.js`

**怎么改**：在轮询 15 秒超时后，不清除状态而是显示提示，并提供重试入口。

```javascript
// 在 clearInterval 之前添加
setTimeout(function() {
    clearInterval(pollTimer);
    // 不是简单清除，而是显示可操作的失败状态
    status.textContent = '⏳ 送达超时 — 请点击按钮重试';
    status.style.cursor = 'pointer';
    status.onclick = function() {
        // 重新发送（重用 sentCache）
        const caches = JSON.parse(localStorage.getItem('sentCache') || '[]');
        const unsent = caches.find(c => !c.sent);
        if (unsent) {
            document.getElementById('awake-editor').value = unsent.text;
            unsent.sent = true; // 标记避免二次发送
            localStorage.setItem('sentCache', JSON.stringify(caches));
            _awakeDoSend(false); // 重发
        }
    };
}, 15000);
```

### 方案 C：（暂不推荐）保持长连接 WebSocket 替代每次新建连接

创建进程内持久 WebSocket 连接（Python 端或独立 Node 进程），复用同一连接发送所有 inject 消息。这样避免每次 inject 的 WebSocket 握手开销和连接失败风险。

**为什么暂不推荐**：
- 架构改动大，需要处理重连、心跳、并发
- 第四代编辑器保持简单进程模型的好处大于性能优化
- 方案 A 已经能解决 99% 的故障

### 方案 D：（可选增强）在 inject-helper 中加入重试逻辑

**改什么**：`/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/inject-helper.mjs` 的 `main()` 函数

在 `chat.send` 发完后，等待 1-2 秒确认，如果 Gateway 返回 close 或 error，重试一次（创建新连接）。

```javascript
// 在 sendFrame 之后，不是立即 exit，而是等待确认
const ack = await recvFrame(2000).catch(() => null);
if (!ack || ack.type === 'close') {
    // 重试一次
    console.error('First attempt failed, retrying...');
    // ... 重新连接并发送
}
```

---

## 5. 推荐实施顺序

```
优先级 P0 ─── 方案 A（等待 inject-helper 确认）
             ├── 解决核心问题：后端不再谎报 ok
             ├── 单文件修改，15 行
             └── 改动前可在生产验证

优先级 P1 ─── 方案 B（前端恢复机制）
             ├── 解决善后：失败后给用户明确状态和重试操作
             ├── 单文件修改，~20 行
             └── 依赖方案 A 或独立部署均可

优先级 P2 ─── 方案 D（helper 重试）
             ├── 进一步提高可靠性
             ├── 单文件修改，~10 行
             └── 可与方案 A 结合使用

推迟 ──── 方案 C（持久 WebSocket）
         ├── 架构变动大
         ├── 当前瓶颈不在连接建立
         └── 留作 v5 考虑
```

---

## 6. 风险提示

### 方案 A 风险

| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| inject-helper 卡住导致前端 timeout | 低 | 15 秒 `timeout` 参数兜底 |
| 增加 ~300ms 延迟 | 中 | 只影响 inject 场景（用户发消息），不影响正常浏览 |
| 日志输出格式变化影响诊断 | 低 | `.inject_logs` 依然写入（Popen 改为 run 后也可以写） |

### 方案 B 风险

| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 重发导致消息重复 | 中 | sentCache 标记防重，idempotencyKey 已在 inject-helper 中实现 |
| 用户误触重发 | 低 | 明确状态文案和交互 |

### 通用风险

- 本报告涉及的所有文件位于 `/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/` 目录
- 第四代编辑器架构不变：`edit-web.py` + `inject-helper.mjs` + 前端 JS
- 方案 A 仅修改后端 Python 文件，不影响前端 HTML/JS
- 所有改动均可逆（回退到 `backup_20260625_v4_current`）

---

## 7. 架构图

```
用户输入 ──→ api.inject(msg) ──→ POST /api/inject
                                      │
                                      ▼
                              inject_via_websocket()
                                      │
                                      ├── 检查 inject lock
                                      ├── 写入 lock file
                                      ├── subprocess.Popen(bun helper)
                                      │      │
                                      │      ▼
                                      │  inject-helper.mjs
                                      │      │
                                      │      ├── TCP connect 127.0.0.1:{GATEWAY_PORT}
                                      │      ├── WebSocket upgrade
                                      │      ├── Gateway auth (connect RPC)
                                      │      └── chat.send RPC
                                      │             │
                                      │             ▼
                                      │         Gateway
                                      │             │
                                      │             ├── 写入 session JSONL
                                      │             └── 传递给 AI model
                                      │
                                      └── 返回 {"ok": True} ← ★ BUG: 不等 helper 完成

前端收到 {"ok": True}
      │
      ├── 乐观更新：添加消息到 store.pairs
      ├── UI 显示消息（看起来已发送）
      └── 启动轮询 /api/session?fresh=1
              │
              ├── 每 1.5 秒检查 pairs.length
              ├── 如果未增长 → "⏳ 等待送达 OpenClaw..."
              └── 15 秒后停止 → 状态卡死
```

**修复后流程（方案 A）**：

```
inject_via_websocket()
      │
      ├── subprocess.run(bun helper, timeout=15)  ← 等待完成
      │      │
      │      ├── 成功 → 返回 {"ok": true}
      │      └── 失败 → raise Exception
      │
      └── 返回 helper 的 真实结果
              │
前端收到 {"ok": True} ← ✅ 此时消息已确认送达 Gateway
```

---

## 8. 附录：相关文件索引

| 文件 | 行数 | 用途 |
|------|------|------|
| `edit-web.py` | 190-262 | `inject_via_websocket()` 核心发送逻辑 |
| `edit-web.py` | 241-248 | **BUG 点**：subprocess.Popen 火抛 |
| `inject-helper.mjs` | 全文件 | WebSocket 连接 + RPC 发送 |
| `awake.js` | 192-249 | `_awakeDoSend()` 前端发送+乐观更新+轮询 |
| `awake.js` | 230-248 | **BUG 交互**：轮询超时后无恢复 |
| `core.js` | 62 | `api.inject` 定义 |
| `core.js` | 238-240 | `refresh()` 乐观消息保留逻辑 |
| `core.js` | 68-72 | 自动轮询 `_pollTimer`（3秒间隔） |
| `editor.js` | 94-139 | `saveEdit()` 截断后 inject |
| `inject_handler.py` | 1-33 | `handle_inject()` 入口 |
| `momo_handler.py` | 26-46 | `inject_feeling` 处理（bypass_lock=True） |
| `session_handler.py` | 18-64 | `handle_get_session_data()` session 快照读取 |
| `router.py` | 56-57 | `/api/session` 路由 |
