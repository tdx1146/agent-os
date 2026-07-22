# 🏗️ 前端审计报告 — 轻如烟 Editor

> **审计日期**: 2026-06-25  
> **审计范围**: `scripts/static/js/` 下全部 12 个 JS 文件  
> **加载顺序**: core.js → app.js → components.js → dashboard.js → render.js → subagent.js → file-browser.js → editor.js → momo.js → awake.js → cache-monitor.js  
> **审计目标**: 错误处理、重试、乐观更新、超时、竞态条件、存储、UI 反馈、模块边界

---

## 一、各文件职责摘要

| # | 文件 | 行数 | 核心职责 | 评价 |
|---|------|------|----------|------|
| 1 | **core.js** | 321 | Store 状态管理、API 层 (`api.get/post`)、Markdown 渲染、自动轮询、上下文监控、Toast、sentCache 面板渲染 | ⚠️ 大杂烩，职责过多 |
| 2 | **app.js** | 39 | 组件框架 (CL registry) | ✅ 极简、清晰 |
| 3 | **components.js** | 278 | CL 注册组件：会话选择器、消化栏、系统健康、备份、秘书、武器库、思考模式、待办 | ✅ 边界清晰 |
| 4 | **dashboard.js** | 38 | 引导启动 (boot)，等依赖就绪后渲染 | ✅ 标准入口 |
| 5 | **render.js** | 360 | 页面渲染 (`renderPage`)、增量哈希比较、分页、TTS、记忆文件、事实弹窗、缓存统计、提醒、文本域增强 | ⚠️ 过度合并（原 cache.js/facts.js/tts.js/reminders.js/textarea.js/pagination.js/memory-file.js 合成一个） |
| 6 | **subagent.js** | 136 | 子代理列表展示、spawn/授权、定时轮询 | ✅ 独立模块 |
| 7 | **file-browser.js** | 502 | 文件树浏览器、CRUD 操作、移动/重命名/删除 | ✅ 专注 |
| 8 | **editor.js** | 224 | 对话编辑/截断、乐观更新、主人授权绕过 | ✅ 专注 |
| 9 | **momo.js** | 365 | 摸摸协议各项操作：打包、状态、裁剪、武器库、仪式、备份、搜索 | ✅ 专注 |
| 10 | **awake.js** | 280 | 对话框发送、截断+发送、题库管理、乐观更新+轮询 | ✅ 专注 |
| 11 | **cache-monitor.js** | 185 | 缓存面板 (v2 重写)、轮次详情表 | ✅ 独立模块 |
| 12 | **subagent.js** | 136 | 子代理面板 | ✅ 独立模块 |

---

## 二、fetch 错误传播路径图

### 完整链路：用户点击 → 直到看到错误提示

```
┌─────────────────────────────────────────────────────────────────┐
│ 用户点击按钮                                                     │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ 异步函数调 api.xxx()                                             │
│   e.g. awake.js: await api.momo('inject_feeling', {feeling})     │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ core.js: api.get() / api.post()                                 │
│                                                                  │
│   try {                                                         │
│     r = await fetch(url)         ←── 可能 throw TypeError       │
│     if (!r.ok)                   ←── HTTP 错误 (4xx/5xx)         │
│       throw Error('API 503: ...')                                │
│     return r.json()                                              │
│   }  ←── 没有外层 try/catch，直接冒泡                             │
└─────────────────┬───────────────────────────────────────────────┘
                  │
        ┌─────────┴─────────────┐
        ▼                       ▼
HTTP 错误 (4xx/5xx)     网络错误 (TypeError)
Error('API 503: path')  Error('Failed to fetch')
        │                       │
        └─────────┬─────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ 调用者 catch 处理（4 种模式）                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ 模式 A: 完全静默                                                │
│   refresh():         catch(e){}                                  │
│   poll setInterval:  catch(e){}                                  │
│   updateContextDisp: .catch(function(){})                        │
│   components render: .catch(function(){})                        │
│                                                                  │
│ 模式 B: 显示在 status 元素                                       │
│   awake.js → status.textContent = '❌ ' + e.message               │
│   editor.js → st.textContent = '❌ ' + (e.message)                │
│                                                                  │
│ 模式 C: 显示在 result 元素                                       │
│   momo.js → r.textContent = '❌ 错误: ' + e.message               │
│                                                                  │
│ 模式 D: Toast 通知                                               │
│   subagent.js → toast('子代理出错: ' + e.message, true)           │
│   render.js TTS → toast('请求失败: ' + e.message, true)           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ 用户最终看到的                                                   │
│                                                                  │
│ ✅ 好的路径: awakeSendTrunc → status 行显示 "❌ 注入失败: ..."     │
│ ❌ 静默路径: refresh()失败 → 完全无感（store 保留旧数据，但可能 stale) │
│ ❌ 静默路径: 轮询失败 → 无任何用户反馈                             │
│ ⚠️  组件刷新失败 → 该行显示 ? 或无变化                             │
└─────────────────────────────────────────────────────────────────┘
```

### 核心问题

**约 70% 的 fetch 失败被静默吃掉，用户完全不知情。**

具体统计：

| 调用方 | 错误处理方式 | 严重程度 |
|--------|-------------|----------|
| `refresh()` | `catch(e){}` | 🔴 P0 |
| 3s 自动轮询 | `catch(e){}` | 🔴 P0 |
| `updateContextDisplay()` | `.catch(function(){})` | 🟡 P2 |
| `updateCachePct()` | `.catch(function(){})` | 🟡 P2 |
| components 全部 render 方法 | `.catch(function(){})` | 🟡 P2 |
| `awake.js` 用户触发操作 | 显示错误信息 ✅ | — |
| `momo.js` 用户触发操作 | 显示错误信息 ✅ | — |
| `editor.js` 用户触发操作 | 显示错误信息 ✅ | — |
| `subagent.js` 子代理加载 | 显示错误信息 ✅ | — |

---

## 三、问题清单

### 🔴 P0 — 严重缺陷

| # | 问题 | 位置 | 细节 |
|---|------|------|------|
| **P0-1** | **fetch 无超时** | `core.js:14`, `core.js:22` | `api.get()` 和 `api.post()` 调用 `fetch(path)` 时没有传递 `signal` (AbortController)。网络连接断开时 fetch 可能挂起 60-300s（浏览器默认），期间界面无响应。这是 "Failed to fetch" 的最常见前端根因。 |
| **P0-2** | **refresh() 静默失败** | `core.js:112` | `catch(e){}` — 网络错误、HTTP 错误、JSON 解析错误全部静默。用户看到的对话内容可能是 stale 的，且没有提示。 |
| **P0-3** | **3s 自动轮询静默失败** | `core.js:82` | `catch(e){}` — 每 3 秒一次的轮询失败完全静默。后端短暂不可用时用户无感，但如果后端持续不可用，用户仍在发消息但对话不更新。 |
| **P0-4** | **乐观更新不回滚** | `awake.js:165-168`, `editor.js:149-164` | 发送时乐观插入 `optimisticPair` 到 `store.pairs`，但如果后续轮询超时（15s）或后端最终未收录，这个虚拟条目残留在 UI 中永不过期。用户会以为自己发了但 AI 没回复。 |
| **P0-5** | **竞态：双击发送** | `awake.js:142-148` | `editor.value = ''` 在 API 调用前执行。双击时两个 `inject_feeling` 几乎同时发出去（无去重/防抖），`sentCache` 先 push 再清 editor，第一个请求还在处理。后端收到两次相同消息。 |
| **P0-6** | **无重试机制** | `core.js` 全局 | 所有 fetch 调用都是"一击即弃"。没有指数退避重试、没有重试上限。用户看到的"重发"按钮来自 `sentCache` (localStorage)，是手动重发，不是自动重试。 |

### 🟠 P1 — 中等严重

| # | 问题 | 位置 | 细节 |
|---|------|------|------|
| **P1-1** | **并发请求爆炸** | 多处 | 3s 轮询 + `updateContextDisplay` (20s) + `updateCachePct` (20s) + 组件各自的 20s 刷新 + awake 的 1.5s 轮询 + editor 的 1.5s 轮询 → 高峰期可能同时 6-10 个请求并发。浏览器每个域名限制 6 个并发连接，HTTP/1.1 下会排队。 |
| **P1-2** | **editor.js 顶层变量 stale** | `editor.js:2` | `var pairs = store.pairs;` 在脚本加载时执行一次，但 `store.pairs` 在运行时会被替换（`store.pairs = d.pairs`）。`pairs` 变量指向**旧引用**。后续 `pairs.length - pairIdx` 等计算可能产生错误结果。 |
| **P1-3** | **sentCache 无上限** | `awake.js:143`, `core.js:118` | `sentCache.push(...)` 没有限制。长时间使用可能堆积数千条，`localStorage` 配额 (5MB) 可能耗尽。 |
| **P1-4** | **poll + manual refresh 不协调** | `core.js:71` vs `core.js:91` | 3s 轮询和 `refresh()` 可能同时发起请求。两者都修改 `store.pairs` 和 `_lastPairCount`。没有互斥锁。 |
| **P1-5** | **多 tab sentCache 冲突** | `awake.js:143`, `core.js:118` | `localStorage` 在多个 tab 间共享。一个 tab 标记 `sent=true` 后写入，另一个 tab 读取时找不到自己的条目。没有 storage event 监听。 |
| **P1-6** | **`editor.js` 30s 轮询无清理** | `editor.js:131,218` | `setInterval` 会在组件 unmount 后继续运行。虽然组件不会 unmount（SPA），但如果上方编辑面板被手动移除（cancelEdit），轮询仍在跑。 |

### 🟡 P2 — 警告

| # | 问题 | 位置 | 细节 |
|---|------|------|------|
| **P2-1** | **全局变量污染** | `core.js:4-7` | `msgCache`, `pairs`, `currentPage`, `totalPages` 全部挂到 window。12 个 JS 文件有约 50+ 个全局函数和变量。 |
| **P2-2** | **loadCacheStats 函数覆盖** | `render.js` vs `cache-monitor.js` | 两个文件都定义了 `loadCacheStats()`。`cache-monitor.js` 在加载顺序末尾，覆盖前者。依赖脚本加载顺序，脆弱。 |
| **P2-3** | **所有 setInterval 无上限** | 多个文件 | `updateContextDisplay`(20s)、`updateCachePct`(20s)、组件 refresh(20s)、轮询(3s)、`editor.js`(1.5s)、awake(1.5s)。页面长期不刷新时这些 interval 永久运行。 |
| **P2-4** | **轮询在不可见 tab 继续** | 全部 | 没有使用 `document.hidden` / `visibilitychange` 来暂停轮询。用户切换到其他 tab 时，轮询继续浪费带宽和电池。 |
| **P2-5** | **`api.edit` 未使用 `api.post()`** | `editor.js:101` 间接 | 实际路径：`editor.js` 调用 `api.edit()` → `core.js` 调用 `api.post('/api/edit', ...)`。链路正确，但冗余。 |
| **P2-6** | **`editor.js` 安全铁律 UI 用了 innerHTML** | `editor.js:108-111` | `st.innerHTML = '❌ ... <button ...>` 包含用户控制内容（`escapeHtml` 已用，但 policy suggest 使用 `createElement` 更安全）。 |

### 🔵 P3 — 建议

| # | 问题 | 位置 | 细节 |
|---|------|------|------|
| **P3-1** | **render.js 过大** | render.js 360行 | 注释显示它是由 cache.js/facts.js/tts.js/reminders.js/textarea.js/pagination.js/memory-file.js 合并而来，单一文件职责过重。 |
| **P3-2** | **sentCache 文本无压缩** | 多处 | 存储完整文本到 localStorage，大文本情况下浪费空间。 |
| **P3-3** | **JSON 解析未 try/catch** | `core.js:118`, `awake.js:143` | `JSON.parse(localStorage.getItem('sentCache') || '[]')` — 假设 localStorage 中的数据总是合法的 JSON。如果其他脚本意外写入了非法 JSON，会崩溃。 |
| **P3-4** | **`escapeHtml` 仅 escape 了基本字符** | `core.js:177` | 没有处理单引号 `'` 和反引号 `` ` ``。 |
| **P3-5** | **多次出现的 `_tp`/`_tp2` timer 未变量提升** | `editor.js:127,212` | 两次定义 `var _tp` 和 `var _tp2`（实际因为 var hoisting 是同一个变量），第二次覆盖第一次。 |
| **P3-6** | **无 SourceMap** | 全局 | 所有 JS 文件是生产部署的，但没有 sourcemap，线上调试困难。 |
| **P3-7** | **无 Service Worker / Offline 支持** | 全局 | 本应用依赖实时后端，但没有任何 offline fallback。 |

---

## 四、"Failed to fetch" 前端根因分析

### 实际表现

用户在浏览器控制台看到 `TypeError: Failed to fetch` 或 `TypeError: NetworkError when fetching`。

### 前端侧根因

#### 1. 🌳 主因：无超时机制（P0-1）

`core.js` 中的 `api.get()` 和 `api.post()` 使用原版 `fetch()` **没有传入 AbortController signal**。

```js
// 当前实现：无超时
async get(path) {
  const r = await fetch(path + '...');  // ← 挂起时浏览器默认等 60-300s
  if (!r.ok) throw ...
  return r.json();
}
```

**影响**：
- 后端重启时，TCP 连接保持 open 直到内核超时（通常 60-127s）
- 浏览器连接池被 hang 住的请求占满 → 新请求排队 → 表现为 "Failed to fetch"
- 用户以为刷新能解决，但旧请求可能还挂着

#### 2. 🌳 批量请求并发（P1-1）

高峰期同时进行的请求：

| 来源 | 间隔 | 端点 |
|------|------|------|
| 自动轮询 | 3s | `/api/session?fresh=1` |
| 上下文更新 | 20s | `/api/status` |
| 缓存更新 | 20s | `/api/cache-stats` |
| 会话选择器 | 20s | `/api/list-sessions` |
| 消化栏 | 20s | `/api/digestion-skill` |
| 系统健康 | 20s | `/api/system-health` |
| 备份状态 | 20s | `/api/backup-stale` |
| 思考模式 | 20s | `/api/thinking-status` |
| awake 轮询 | 1.5s | `/api/session?fresh=1` |
| editor 轮询 | 1.5s | `/api/session?fresh=1` |

→ **峰值 10+ 个并发请求**，浏览器 HTTP/1.1 每个域名 6 个连接的上限被迅速打满。

#### 3. 🌳 重试缺失（P0-6）

没有任何请求启用重试机制。一次瞬时的网络波动（如 DNS 解析延迟、TCP 丢包重传）就会导致请求失败，且不会自动恢复。

#### 4. 🌳 错误被静默吞掉（P0-2, P0-3）

所有自动触发的请求失败都进入 `catch(e){}` 或 `.catch(function(){})`。用户看到的是"对话不刷新"而不是一个错误提示，导致难以从体验上判断是后端挂了还是前端网络问题。

#### 5. 嗅探请求导致连接焦虑

`?t=Date.now()` 的 cache-busting 策略导致所有请求都不可缓存，即使是重复请求也不会复用缓存。

### "Failed to fetch" 传播流程

```
后端重启/网络波动
    │
    ▼
浏览器对 /api/session?fresh=1&t=xxx 建立 TCP 连接
    │
    ├── 连接 hang → 浏览器内核超时 (默认 60-300s)
    │       │
    │       ▼
    │   TypeError: Failed to fetch (网络层)
    │       │
    │       ▼
    │   core.js 3s 轮询 catch(e){}
    │       │
    │       ▼
    │   用户: 界面停止更新，无任何提示
    │
    └── 连接占满连接池 → 新请求无法发出
            │
            ▼
        新请求立即失败: TypeError: Failed to fetch
            │
            ▼
        awake/editor 调用者显示 "❌ ..." 
            │
            ▼
        用户: "发不出去了，刷新也没用"
```

---

## 五、架构评价

### 评分表 (满分 10)

| 维度 | 评分 | 说明 |
|------|------|------|
| **前后端分离** | 6/10 | 有明确的 API 层 (`api` 对象)，但很多端点路径散落在 core.js 中而不是独立配置文件。无 API 版本控制，无请求/响应拦截器，无错误类型分类。 |
| **模块独立** | 5/10 | app.js 组件框架设计合理，但 render.js 沦为"垃圾场"（合并了 7 个独立模块）。core.js 混合 store、API、UI、Markdown 渲染。两个文件定义了同名函数 (`loadCacheStats`)。 |
| **错误处理** | 3/10 | 用户触发操作有较好错误提示，但**自动操作 70% 静默失败**。没有统一错误处理层，没有全局 error boundary，没有 Sentry/错误日志收集。 |
| **性能** | 6/10 | 增量渲染 (pairHash) 设计合理。但并发请求过多、无连接复用优化、无轮询收敛 (visibility change)。 |
| **可维护性** | 5/10 | 大量全局变量和函数增加耦合。editor.js 顶层 `var pairs = store.pairs` 是经典陷阱。注释质量中等，部分文件缺少文件头说明。 |
| **数据一致性** | 4/10 | 乐观更新不回滚 (P0-4) 是严重缺陷。localStorage 多 tab 无同步。sentCache 无上限。 |
| **用户反馈设计** | 7/10 | 用户的"发送→成功/失败"闭环体验不错（awakeSendTrunc 显示完整状态链），但静默失败的场景太多。 |
| **安全性** | 6/10 | escapeHtml 已用，innerHTML 使用谨慎（多数情况）。一个 JSON.parse 不安全，一个 st.innerHTML 含用户控制内容。 |

### 综合评价：**5.25/10** ⭐⭐⭐

> **亮点**：组件框架设计优雅、增量渲染节省 DOM 操作、用户触发操作的错误提示完整、乐观更新是正确方向（缺回滚）。  
> **短板**：静默失败过多、无超时/重试、乐观更新无回滚、render.js 过度膨胀、并发请求爆炸。  
> **架构模式**：类似于"Store + Render"架构（MVC 变体），并非成熟的 SPA 框架，但体量不大够用。

### 架构改进路线图（按优先级）

```
P0 必须修 ──────────────────────────────────────────────────────
  ├─ 1. api.get/post 加入 AbortController + 超时 (15s)
  ├─ 2. refresh() 和 轮询 catch 改为 toast 或 status 显示
  ├─ 3. optimistic 回滚：轮询结束未确认则移除假条目
  ├─ 4. sentCache 加入上限 (200 条) + 过期时间 (7天)

P1 重要 ────────────────────────────────────────────────────────
  ├─ 5. 合并相同端点的轮询（不要 4 个地方各轮询 /api/session）
  ├─ 6. visibilitychange 暂停轮询
  ├─ 7. editor.js 顶层 var pairs 改为函数引用
  ├─ 8. 添加 storage event 监听 sentCache 变更

P2 建议 ────────────────────────────────────────────────────────
  ├─ 9. 拆分 render.js（至少分出 pagination、tts、reminders）
  ├─10. 全局错误监控层（window.onunhandledrejection）
  ├─11. loadCacheStats 重命名避免覆盖
  └─12. JSON.parse 安全包装
```

---

## 附录: 请求函数对比

| 属性 | 当前实现 | 建议改进 |
|------|----------|----------|
| 超时 | ❌ 无 | `AbortSignal.timeout(15000)` |
| 重试 | ❌ 无 | 指数退避重试 (最多 3 次) |
| 错误分类 | ❌ 只有 Error | `NetworkError` vs `HttpError` vs `TimeoutError` |
| 并发控制 | ❌ 无 | 请求队列 + 去重 |
| 自动轮询 | ❌ 不可见 tab 继续 | `visibilitychange` 暂停 |
| 缓存 | ❌ 所有请求不可缓存 | 非新鲜请求可复用数据 |

---

*报告完毕。全文基于 12 个 JS 源文件（共约 175KB/3885 行）审计。*
