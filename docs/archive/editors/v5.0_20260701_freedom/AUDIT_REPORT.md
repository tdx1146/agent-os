# 轻如烟 Edit-Web 架构审计报告

> 审计日期：2026-06-25  
> 审计范围：edit-web.py (3925行) + handlers/ (8文件) + utils/ (6文件) + static/js/ (11文件, ~2972行) + inject-helper.mjs (359行)  
> 审计原则：前后端分离、模块独立、变量统一、可回溯、可迭代

---

## 1. 架构总览图（ASCII）

```
┌──────────────────────────────────────────────────────────────┐
│                        浏览器 (用户界面)                       │
│  static/js/ (11 files, ~2972行)                               │
│  ├─ app.js          ─ 组件框架 (CL.register)                   │
│  ├─ core.js         ─ API封装(api.get/post) + 轮询 + toast     │
│  ├─ render.js       ─ 消息渲染 (Markdown→HTML)                │
│  ├─ editor.js       ─ 截断编辑流程                             │
│  ├─ momo.js         ─ 摸摸面板 + 打包/搜索/恢复               │
│  ├─ dashboard.js    ─ 四灯状态面板                             │
│  ├─ file-browser.js ─ 文件浏览器                              │
│  ├─ cache-monitor.js─ 缓存监控 (独立组件)                      │
│  ├─ components.js   ─ 通用UI组件                              │
│  ├─ subagent.js     ─ 子代理面板                              │
│  ├─ awake.js        ─ 守夜面板                                │
│  └─ index.html      ─ 单页入口 (2.2KB)                       │
└───────────────┬──────────────────────────────────────────────┘
                │ HTTP (端口 EDITOR_PORT, 默认18888)
                │ 请求路径: /api/xxx, /static/xxx, /
                ▼
┌──────────────────────────────────────────────────────────────┐
│                    HTTP 服务器层 (edit-web.py)                │
│                                                               │
│  ThreadingHTTPServer (Handler class, ~270行HTTP处理)          │
│  ├─ do_GET()      ─→ handlers/router.py:get()                 │
│  ├─ do_POST()     ─→ handlers/router.py:post()                │
│  ├─ _send_json()  ─ 统一JSON响应 (含gzip压缩)                 │
│  ├─ _serve_static_file() ─ 静态文件服务                        │
│  ├─ _get_query_param()    ─ 查询参数提取                      │
│  └─ V6Server/V6HttpsServer ─ IPv4/IPv6双栈HTTPS               │
└───────────────┬──────────────────────────────────────────────┘
                │ 路由分发
                ▼
┌──────────────────────────────────────────────────────────────┐
│            路由层 (handlers/router.py, ~150行)                │
│                                                               │
│  get()  — 30+ GET路由                                        │
│  post() — 20+ POST路由                                       │
│  通过 _M 模块引用 + g() 全局函数调用 edit-web.py中的函数      │
│  错误处理：不存在的路径 → 404 {"ok":False,"error":"not found"} │
└───────────────┬──────────────────────────────────────────────┘
                │ 函数调用
                ▼
┌──────────────────────────────────────────────────────────────┐
│           业务逻辑层 (edit-web.py 内联 + handlers/*.py)        │
│                                                               │
│  edit-web.py 内 (≈2300行业务函数 + 600行配置+主入口):         │
│  ├── 配置发现 (50行)  ── env > editor-config.json > openclaw │
│  ├── inject_via_websocket() ─ 发起WS注入 (bun子进程)         │
│  ├── edit_message()          ─ 截断会话文件                  │
│  ├── list_all_sessions()     ─ 列所有会话                    │
│  ├── read_session()          ─ 读会话文件(快照保护)           │
│  ├── _momo_pack/status/index_report ─ 摸摸协议                │
│  ├── _digestion_xxx系列     ─ 消化循环状态                    │
│  ├── _plugin_health系列     ─ 插件健康检查                    │
│  ├── _send_pulse()          ─ 守夜脉冲                       │
│  ├── _exec_subagent()       ─ 直接API子代理                  │
│  ├── _spawn_subagent_process() ─ Gateway RPC子代理            │
│  ├── _search_backups()      ─ 备份搜索                       │
│  ├── 加密系统 (XOR + AES)    ─ 加密/解密                    │
│  ├── 文件变更追踪            ─ diff log                     │
│  └── 守夜题库 (唤醒题库.md)   ─ 问题随机选择               │
│                                                               │
│  handlers/  (迁移中, 每个文件1-3个函数, 总计≈100行):          │
│  ├── inject_handler.py   ─ WS注入 (内存锁, 仅13行)          │
│  ├── crypto_handler.py   ─ 加密处理器                        │
│  ├── file_handler.py     ─ 文件操作                          │
│  ├── helper_handler.py   ─ 辅助函数                          │
│  ├── momo_handler.py     ─ 摸摸打包                          │
│  ├── session_handler.py  ─ 会话操作                          │
│  └── system_handler.py   ─ 系统状态                          │
│                                                               │
│  utils/ (已拆分模块, 自包含函数, ≈600行):                     │
│  ├── tb_handler.py     ─ 文件读写/列举/创建/删除/重命名     │
│  ├── momo.py           ─ 摸摸打包/状态/索引/自动存档        │
│  ├── secretary.py      ─ 提醒管理 + 文件变更追踪            │
│  ├── session.py        ─ 会话文件读/写/截断                 │
│  ├── inject.py         ─ WS注入 (内存锁, 双轨过渡)          │
│  └── crypto.py         ─ 加密解密工具                       │
└───────────────┬──────────────────────────────────────────────┘
                │ subprocess.Popen (异步)
                │ subprocess.run (同步)
                ▼
┌──────────────────────────────────────────────────────────────┐
│          外部进程层 (Inject + Gateway + API)                 │
│                                                               │
│  inject-helper.mjs (359行)                                    │
│  ├── 功能：通过WebSocket连接到Gateway                          │
│  │   ├── chat.send    ─ 发送消息到session                    │
│  │   ├── chat.abort   ─ 中止AI思考                          │
│  │   └── chat.history ─ 获取历史消息                          │
│  ├── 认证：Token + deviceId = "openclaw-control-ui"          │
│  │   └── dangerouslyDisableDeviceAuth = true (硬编码)        │
│  └── 超时：connect 2s, abort 5s, history 10s, send fire&forget│
│                                                               │
│  Gateway (外部进程, 端口 GATEWAY_PORT)                        │
│  ├── WebSocket服务器 (chat.send/abort/history)               │
│  ├── Agent管理 (agent.spawn)                                 │
│  └── 设备管理 (device.requestApproval)                       │
│                                                               │
│  外部API (直接HTTP调用):                                      │
│  ├── DeepSeek API ─ deepseek-chat                            │
│  ├── GLM API     ─ GLM-Z1-Flash                              │
│  └── 混元 API   ─ hunyuan-instruct/thinking                  │
└──────────────────────────────────────────────────────────────┘

                文件/磁盘层
┌──────────────────────────────────────────────────────────────┐
│   DATA_DIR   (sessions/ + *.jsonl)                            │
│   BACKUP_DIR (backups/ + pre-edit.*.jsonl, 96份)             │
│   MOMO_DIR   (找回自己/ + README + 身份文件 + daily/)        │
│   LIGHT_SMOKE_DIR (memory/ + facts.dict.md + 秘书观察.log)  │
│   /tmp/      (plugin-injected.txt, last-processing.txt ...)  │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. 问题清单（按严重程度分级）

### 🔴 P0 — 会导致服务器 crash 或数据丢失

#### P0-1: `_handle_restart_http` 中的 `os.kill(os.getpid())` 直接杀死进程
- **文件**: edit-web.py, `_handle_restart_http` 方法
- **描述**: 重启逻辑在发送HTTP响应后通过 `os.kill(os.getpid(), 9)` 杀死当前进程，然后 `sp.Popen` 启动新进程。新进程启动路径在 `cd '{script_dir}'` 和 `exec python3 '{script_path}'` 之间有时间窗口，期间没有服务器在监听端口 — 所有正在处理的请求都会丢失。
- **根因**: 使用 `SIGKILL` (`kill -9`) 而非 `SIGTERM` 优雅关闭。`ThreadingHTTPServer.serve_forever()` 被强行终止时，正在处理的请求（包括**当前正在截断会话的请求**）不会等到写盘完成。
- **触发概率**: 中 — 点击「重启HTTP服务」按钮即可触发。
- **影响**: 正在保存的文件可能损坏；正在截断的会话可能只写了一半。

#### P0-2: `inject_via_websocket` 在 `bypass_lock=True` 时仍调用 `_cleanup_lock()`，存在竞态
- **文件**: edit-web.py, `inject_via_websocket()` 函数 (≈第390行)
- **描述**: 当 `bypass_lock=True`（绕过安全锁注入，如妹妹消息、守夜发送），函数在 `subprocess.Popen` 后立刻调用 `_cleanup_lock()`。但函数开头写入锁文件时没有区分 bypass 模式 — 锁文件被写入后又被立即删除。
- **更严重的问题**: 对于 `bypass_lock=True` 的调用，函数执行路径: 写入锁 → subprocess.Popen(异步) → _cleanup_lock(删除锁)。随后正常注入会看到锁文件不存在，触发正常注入，导致两条消息同时注入到 session。
- **根因**: `_cleanup_lock()` 调用位置不对。`bypass_lock=True` 时锁文件不应写入；`bypass_lock=False` 时锁文件不应在子进程返回前被删除。

#### P0-3: `edit_message` 备份后在 `session_file` 上直接写 `"w"` 模式截断
- **文件**: edit-web.py, `edit_message()` 函数
- **描述**: 备份后使用 `open(session_file, "w").write(...)` — 这将**截断原文件再写入**。如果写入过程中进程崩溃，原文件数据完全丢失。只有备份能恢复，但备份在 BACKUP_DIR 中，不是即时自动恢复的。
- **数据丢失场景**: 写入过程中 kill 进程、磁盘满、OS OOM — 原 `session_file` 只剩半截数据，备份文件完整。
- **根因**: 没有使用原子写入（write-to-temp + rename）。

#### P0-4: `edit_message` 保险线检查存在逻辑缺陷可被绕过
- **文件**: edit-web.py, `edit_message()` → `lines_to_truncate > total_lines // 2` 检查
- **描述**: 保险线检查 `if lines_to_truncate > total_lines // 2`，意味着截断量正好等于一半时通过检查（≤总行数50%）。但一个 2000 行会话的后 1001 行被拒绝，后 1000 行被允许。更危险的是：如果备份文件中只有 3 行，截断 1 行（保留 2 行）是 33% 通过检查；如果有 100 行，一个用户消息在 50 行处被截断（保留 50 行=50%）也通过。这在「截断倒数第2轮」场景中完全合理。
- **真正的漏洞**: `user_index` 校验的是**用户消息的位置序号**而非**轮数序号**。前端在 `editor.js` 中传的是 `pair.userIndex`，该 index 是 `get_session_data` 中的**从0递增的用户消息序号**。如果对话中有 toolResult 消息，用户消息序号不一定等于对话轮数。如果前端意外传入一个非常大的 userIndex（如来自另一会话的 index），后端仍按自己的 `user_positions` 列表校验，可能导致意外截断。
- **根因**: 保险线检查只校验行数百分比，未校验「截断所删除的用户消息对话轮数」与「当前最新轮数」的关系。

#### P0-5: `INJECT_LOCK_FILE` 文件锁机制在 `subprocess.Popen` 异步释放后存在时序竞争
- **文件**: edit-web.py, `inject_via_websocket()` 和 `_cleanup_lock()`
- **描述**: 函数先写入锁文件（开始时间戳），然后 `subprocess.Popen`（不等待完成），接着立即 `_cleanup_lock()`（删除锁文件）。从 Popen 启动到子进程实际发送 WebSocket 帧之间有几 ms 到几百 ms 的延迟。在这期间，另一个注入请求（如快速连续点击「注入」按钮）会发现锁文件不存在，通过安全检查，触发第二次注入。
- **根因**: 锁文件的存活时间（写入到删除）短于子进程完成注入的实际时间。`subprocess.run`（同步）才能正确保护。

#### P0-6: `_handle_restart_http` 最后一个 `try` 子句中 `self.wfile.flush()` 接 `os.kill`，且该子句前面匹配到 `self._handle_thinking_toggle` 后缺少 `return`，导致控制流向下穿透
- **文件**: edit-web.py, 两个 `_handle_restart_http` 类型的处理函数
- **描述**: 在代码浏览中看到 `_handle_restart_http` 方法最后有个裸 `try` 块，里面 `self.send_response` 后接 `self.wfile.flush()` 然后是 `os.kill(os.getpid())`。更严重的是，其前面的 `_handle_thinking_toggle` 调用后**没有 `return` 语句**，导致 `_handle_thinking_toggle` 完成后继续执行到 `_handle_restart_http` 内部的 kill 代码 (虽然通常不会触发，因为切换思考模式的响应已经发出了)。
- **根因**: 函数边界不清。`_handle_thinking_toggle` 函数内嵌了 restart HTTP 的副作用代码（可能是 copy-paste 遗留）。

---

### 🟠 P1 — 导致功能不可用或用户可见错误

#### P1-1: CORS/OPTIONS 预检完全缺失
- **文件**: edit-web.py, `Handler` 类
- **描述**: Handler 只实现了 `do_GET` 和 `do_POST`，**没有实现 `do_OPTIONS`**。浏览器对 POST 请求发送 `Content-Type: application/json` 时，如果后端跨域，会先发 OPTIONS 预检。当前服务器收到 OPTIONS 请求会返回 404（因为 router 中没有匹配路径）。
- **实际影响**: 如果前端从不同的源（如 `localhost:3000` dev server 或反向代理）访问，所有 POST 请求都会因 CORS 预检失败而无法发送。当前场景下，前后端同源（HTTP + 静态文件在同一端口）所以暂时 OK，但限制了灵活部署。
- **根因**: 没有实现 OPTIONS 处理器。`Access-Control-Allow-Origin: *` 只在 `_send_json` 响应头中有，OPTIONS 预检请求连 `_send_json` 都没走到。

#### P1-2: 前端 API 层不区分「网络错误」「HTTP 错误」「业务错误」
- **文件**: static/js/core.js, `api.get()` 和 `api.post()`
- **描述**: `api.get()` 的实现是：
  ```js
  const r = await fetch(path);
  if (!r.ok) throw new Error('API ' + r.status + ': ' + path);
  return r.json();
  ```
  三种错误被完全统一成 `Error('API 500: /api/xxx')` — 不区分：
  - **网络错误**（fetch 抛出 TypeError: Failed to fetch）
  - **HTTP 错误**（5xx, 4xx）
  - **业务错误**（{ok: false, error: "xxx"}）
  
  调用方如 `editor.js` 的 `saveEdit` 使用统一的 `catch(e)` 显示「网络错误: xxx」，但实际上错误可能是服务器返回的业务错误数据被 `catch` 捕获。
- **根因**: `api.post()` / `api.get()` 在 `!r.ok` 时直接 throw，没有尝试读取 `r.json()` 来区分 HTTP 层错误和业务层错误。

#### P1-3: `/api/ping` 硬编码在 do_POST 中而非路由层
- **文件**: edit-web.py, `do_POST()` 方法
- **描述**: `/api/ping` 的响应逻辑直接写在了 `do_POST()` 函数中，而不是交给 `_router.post()` 处理。这意味着所有 POST 请求的日志、错误处理、统一格式都被绕过。更严重的是，如果 router.py 中的 post 函数需要修改，ping 端点会保持旧状态。
- **根因**: 最早开发时快速添加的端点，后续路由系统重构后没有迁移过来。

#### P1-4: `_handle_tb_read_file` 对 .docx 文件解密只返回 `[docx 读取失败: ...]` 字符串而非错误标志
- **文件**: edit-web.py, `_handle_tb_read_file()`
- **描述**: 当 docx 读取失败时，返回 `{"ok": true, "content": "[docx 读取失败: ...]", "note": "..."}` — `ok` 字段为 `true`，前端无法通过 `!d.ok` 判断读取失败，只能看到内容开头是 `[docx 读取失败:`。
- **根因**: 错误处理不当，将错误信息编码在成功响应中。

#### P1-5: `_handle_api` 的 `action=edit` 中错误地给前端传递 old session_key
- **文件**: edit-web.py, `_handle_api()` 中 `action == 'edit'` 分支
- **描述**: `sk, sf = get_session_info()` 获取的 `sk` 和 `sf` 在函数开头就被赋值，但从未用于 `edit_message` 调用 — `edit_message` 直接从第二个参数 `sf` 获取文件路径。但 `sk` 变量被声明后未使用（lint 未报），这不是功能性问题，而是维护隐患。

#### P1-6: 前端自动轮询（3秒间隔）与截断编辑流程存在竞态
- **文件**: static/js/core.js, `_pollTimer` (setInterval, 3000ms)
- **描述**: 自动轮询每3秒调用 `/api/session?fresh=1`，如果结果有变化就调用 `refresh()` 重设 `store.pairs`。但`editor.js` 的 `saveEdit()` 在截断后调用 `renderPage()`、`store.pairs = d.pairs`。如果轮询在 `saveEdit` 写 store 的同时触发，`store.pairs` 可能被旧数据覆盖。
- **根因**: 没有互斥锁。轮询和编辑操作在不同 async 上下文中并发操作同一个 `store.pairs`。

---

### 🟡 P2 — 架构不合理但当前可用

#### P2-1: 双轨过渡模式长期未清理，edit-web.py 仍然膨胀到 3925 行
- **文件**: 全局
- **描述**: `edit-web.py` 中有大量 `# 🚧 已迁移到 utils/xxx — 此函数体为双轨过渡，稳定后删除` 的注释。但原函数体仍然保留了完整的实现代码。这意味着：
  - `_momo_pack()` 有两份完整代码（edit-web.py + utils/momo.py）
  - `_momo_status()` 有两份完整代码
  - `_momo_index_report()` 有两份完整代码
  - `inject_via_websocket()` 有两份代码（edit-web.py + utils/inject.py）
  - 秘书函数有三份（edit-web.py + utils/secretary.py + handlers/ 中的调用）
  - 加密函数有两份代码（edit-web.py 内联 + utils/crypto.py）
- **影响**: 修改一个功能必须同时维护两个文件。双轨过渡从 5月持续至今未清理，已产生代码腐化。
- **根因**: 重构缺少时间线（deadline）。「稳定后删除」没有定义「稳定」的标准。

#### P2-2: `handlers/` 目录中大部分文件是空的骨架
- **文件**: handlers/inject_handler.py, crypto_handler.py, file_handler.py, helper_handler.py, momo_handler.py, session_handler.py, system_handler.py
- **描述**: `handlers/` 目录的 8 个文件（不包括 `__init__.py` 和 `router.py`）中，`inject_handler.py` 只有 docstring 注释，没有一个实际函数体。所有处理逻辑仍然在 `edit-web.py` 的 `Handler` 类方法中。`__init__.py` 为空（`pass`）。
- **影响**: 虽然 `router.py` 通过 `g()` 全局函数引用 `edit-web.py` 中的函数，但这意味着路由层直接从 `_M`（`edit-web.py` 的 module）中获取函数。这是**伪分离** — 修改路由不需要改 router.py 以外的文件，但 handler 文件就像「文件的墓碑」一样存在误导性。
- **根因**: 过早创建空 handler 文件，但从未真正迁移逻辑进去。

#### P2-3: 硬编码路径散落各处（10+处）
- **文件**: edit-web.py 和 inject-helper.mjs
- **描述**:
  - `/var/apps/bunjs/target/bin/bun` — 在 4 个地方硬编码
  - `/vol1/@apphome/trim.openclaw/data/home/.openclaw/` — 在 8 个地方直接硬编码
  - `/vol1/@apphome/trim.openclaw/data/workspace/hooks` — `_momo_pack` 中
  - `/vol1/@apphome/trim.openclaw/data/home/.pi/agent/skills/` — `_digestion_skill_status` 和 `_momo_pack` 中
  - `/tmp/digestion-last-output.txt` — 在 `_digestion_skill_status` 和 `_promote_pending_assertions` 中
  - `/tmp/last-injection-body.txt`, `/tmp/last-injection.txt`, `/tmp/plugin-injected.txt` — 多个函数
  - 配置文件中的 `/vol1/@apphome/trim.openclaw/` 前缀在 `inject-helper.mjs` 的 `idPath` 中也假设了
- **影响**: 迁移到新机器时，这些路径需要逐一修改。虽然配置发现系统（env > editor-config.json > openclaw.json）已经覆盖了主要路径，但 bun 路径、OpenClaw 安装路径、/tmp 状态文件等没有纳入配置管理。
- **根因**: /tmp 文件用于跨进程状态共享（plugin-helper 写状态给 edit-web 读），没有替代设计。

#### P2-4: `/api/session` 和 `/api/session-rpc` 存在两个不同的会话读取路径
- **文件**: edit-web.py, router.py
- **描述**: `/api/session` 通过文件快照读取 session JSONL。`/api/session-rpc` 通过启动 `gateway-history.js`（一个 node 脚本，在代码中引用）来调用 Gateway RPC。两者返回的数据结构不完全相同（session 返回 pairs，session-rpc 返回 raw_messages）。前端同时使用两者，但没有一致性保证。
- **影响**: 如果 Gateway 写入 session 文件和文件快照之间存在延迟（或者前端刚完成一次截断，文件已更新但 Gateway 内部状态还没刷新），两个 API 可能返回不一致的数据。
- **根因**: 双轨读取策略 — 文件直接读更快但可能冲突，RPC 更权威但更慢。

#### P2-5: 前端 store (全局变量) 缺乏统一状态管理
- **文件**: static/js/core.js, 全局 `store` 对象
- **描述**: `store.msgCache`, `store.pairs`, `store.currentPage`, `store.totalPages` 作为全局变量直接读写。多个模块直接修改 `store.pairs`：轮询线程、editor.js 的 saveEdit、saveEditWithApproval、refresh。没有 mutation 事件通知机制，没有 immutable 保证。
- **影响**: 同一页面中，`render.js` 在渲染时读取 `store.pairs`，但轮询线程可能在渲染中间修改它。渲染结果可能不一致。
- **根因**: 没有使用响应式框架（React/Vue）。原生 JS 单例 store 缺少状态变更通知。

#### P2-6: 子进程模型存在文件描述符泄露风险
- **文件**: edit-web.py, `inject_via_websocket()` 和 `_send_pulse()`
- **描述**: `subprocess.Popen` 的 `stdout=logf` 或 `stdout=subprocess.DEVNULL`。在 `inject_via_websocket` 中，试图打开日志文件 `logf = open(...)`，如果失败则用 `subprocess.DEVNULL`。但 `Popen` 后没有显式关闭 `logf` — 虽然 Python 的垃圾回收会在 `inject_via_websocket` 返回后关闭，但子进程还在运行且继承了 fd。多次快速点击注入可能导致大量打开的文件描述符（每个子进程都继承了 log file fd）。
- **根因**: 没有在 `Popen` 后 `logf.close()`。虽然 `close_fds=True` 是 Python 3.2+ 的默认值（但不适用于 `stdout=` 显式传入的文件对象）。

---

### 🔵 P3 — 代码风格、可维护性

#### P3-1: `_momo_index_report` 中的 `estimated_user_messages` 估值逻辑有缺陷
- **文件**: edit-web.py, `_momo_index_report()`
- **描述**: `total_user_msgs *= min(backup_count, 5)` — 用户消息数乘以 `min(backup_count, 5)`，意思是「5份备份中的用户数 × 备份总数」，这在样本选取上毫无意义。实际用户消息数远比估算值大。
- **根因**: 原代码用 `files[0]`（最早备份）的用户数乘以备份数，但最早的备份通常包含最多消息，而最近备份包含最少消息（因为截断只在最近对话上操作）。

#### P3-2: 重复导入和局部 import 散乱
- **文件**: 全局
- **描述**: `import json`, `import os`, `import datetime` 等模块在函数体内反复导入（局部 import）。`json.loads` 在 `_handle_api` 的 try 前被使用，try 内又有 `json.loads`。很多函数开头做 `import json as _json` 只是为了加载一个文件。
- **影响**: 每次函数调用都重新 import，少量性能损耗。更重要的是，代码可读性降低。

#### P3-3: `_digestion_skill_status` 中的注释编号重复
- **文件**: edit-web.py, `_digestion_skill_status()`
- **描述**: 代码中的注释：
  ```
  # 2. 下次消化时间（从 cron 配置读取） — 实际是第二个 #2
  ```
  注释编号 #2 出现了两次（一个是 `last_digest_time`，一个是 `next_digest_time`）。

#### P3-4: `edit_message` 函数中 `for p in pairs:` 的 `userIndex` 赋值反转
- **文件**: edit-web.py, `get_session_data()` → `reversed_pairs`
- **描述**:
  ```python
  for p in pairs:
      idx += 1
      reversed_pairs.insert(0, {**p, "userIndex": idx})
  ```
  这里 `idx` 从 0 开始递增（最早的用户消息=index 0，最新=index N-1），但 `insert(0)` 把最早的 pair 放到列表最前面，所以 `reversed_pairs` 中 index=0 的元素的 `userIndex` 是 N-1（最大的），最后一个元素的 `userIndex` 是 0（最小的）。前端通过 `pair.userIndex` 传给后端的截断 API，但 `userIndex=0` 在 `edit_message` 中会被解读为「最早的用户消息」。
  - 实际上前端每次都传对了（因为 `pair.userIndex` 在前端遍历 `store.pairs` 时获取），但代码**逻辑反向**增加了维护者理解成本。

#### P3-5: `_handle_restart_http` 方法后的裸 try 块格式异常
- **文件**: edit-web.py, `_handle_thinking_toggle()` 末尾
- **描述**: 代码末尾有一段裸 `try:` 块（不在任何函数体内）：
  ```python
  except Exception as e:
      self._send_json(500, ...)
  ```
  这是 Python 语法错误 — `except` 不能单独存在。这说明代码可能在阅读时被截断，或者这段代码从未被执行到。但从代码结构看，这是全局作用域，会立即导致 `SyntaxError` 并阻止服务器启动。这需要紧急验证。

#### P3-6: `_backup_stale_status` 中 `os.path` 被当作模块名使用
- **文件**: edit-web.py, `_backup_stale_status()` 通过 `__import__('datetime')` 使用
- **描述**: 没有用 `from datetime import datetime` 的全局导入，而是用 `__import__('datetime').datetime.now()` 的 runtime import 方式。虽然功能正确，但在其他函数中用不同的方式导入相同模块（一些用 `from datetime import datetime`，一些用 `import datetime`），风格不一致。
- **频率**: 整个文件中至少有 5 种不同的 datetime 导入方式。

---

## 3. 模块依赖图

```
                    ┌─────────────┐
                    │  index.html │
                    └──────┬──────┘
                           │ file: index.html
                           │ ─→ static/js/app.js
                           │ ─→ static/js/core.js
                           │ ─→ static/js/render.js
                           │ ─→ static/js/editor.js
                           │ ─→ static/js/momo.js
                           │ ─→ static/js/dashboard.js
                           │ ─→ static/js/file-browser.js
                           │ ─→ static/js/cache-monitor.js
                           │ ─→ static/js/components.js
                           │ ─→ static/js/subagent.js
                           │ ─→ static/js/awake.js
                           ├── (所有JS互相通过全局变量/函数耦合)
                           │     core.js 定义: api, store, refresh, toast
                           │     editor.js 使用: api, store, refresh, renderPage
                           │     momo.js 使用: api
                           │     dashboard.js 使用: api, updateContextDisplay
                           │     file-browser.js 使用: api
                           └── 依赖方向
                               core.js ← editor.js (强)
                               core.js ← momo.js (弱)
                               core.js ← dashboard.js (弱)
                               core.js ← file-browser.js (弱)

    ┌────────────────────── HTTP ──────────────────────────┐
    ▼                                                     ▼
┌─────────────┐                               ┌───────────────────┐
│ edit-web.py │ ◄──── handlers/router.py ──── │  static/*.html/js │
│ (3925行)    │     (路由分发, ≈150行)         └───────────────────┘
└──────┬──────┘
       │ 内部调用
       ├──→ inject_via_websocket() ──→ inject-helper.mjs (subprocess)
       │                                └──→ Gateway (WS)
       │
       ├──→ edit_message() ──→ 读写JSONL文件 + BACKUP_DIR
       │
       ├──→ list_all_sessions/session_info ──→ DATA_DIR/sessions.json
       │
       ├──→ read_session() ──→ session_file (.jsonl, 快照保护)
       │
       ├──→ _momo_pack/status/index_report ──→ MOMO_DIR
       │    └── utils/momo.py (相同功能, 双轨)
       │
       ├──→ _digestion_xxx ──→ memory/ + /tmp/ + CRON_JSON
       │
       ├──→ 加密系统 ──→ utils/crypto.py (双轨)
       │
       ├──→ 提醒系统 ──→ utils/secretary.py (双轨)
       │
       ├──→ 文件系统 ──→ utils/tb_handler.py (+ BROWSE_ROOT)
       │
       ├──→ 会话系统 ──→ utils/session.py (双轨)
       │
       ├──→ subprocess ──→ openclaw CLI (cron run, agent等)
       │
       └──→ _exec_subagent() ──→ DeepSeek/GLM/混元 API (HTTP)

    外部文件依赖（只读/写）:
    ├── editor-config.json         (配置)
    ├── OPENCLAW_HOME/openclaw.json (Gateway配置)
    ├── OPENCLAW_HOME/cron/jobs.json (定时任务)
    ├── BROWSE_ROOT/               (浏览根目录)
    ├── LIGHT_SMOKE_DIR/memory/    (各种 MD/JSONL 文件)
    ├── BACKUP_DIR/                (96份预编辑备份)
    ├── MOMO_DIR/                  (找回自己/ 便携备份)
    ├── /tmp/*.txt                 (插件健康状态)
    └── 唤醒题库.md                (守夜问题库)

    模块耦合度总结:
    ⚠️  edit-web.py 自身高内聚(3925行一个文件)
    ⚠️  handlers/ 是"伪模块"(router.py有效,其余为空)
    ⚠️  utils/ 是"真模块"但 edit-web.py 保留副本 → 双轨
    ⚠️  前端12个js文件通过全局变量耦合
    ⚠️  inject-helper.mjs 独立,无其他依赖
    ⚠️  socket 状态通过 /tmp/ 文件跨进程共享(脆弱)
```

---

## 4. 错误传播路径

### 完整路径：浏览器 → edit-web → subprocess → Gateway → 返回

```
┌────────────────────────────────────────────────────────────────────────────┐
│ 场景 A: 用户点击「截断+发送」 (saveEdit)                                  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ① 浏览器 (editor.js: saveEdit)                                           │
│     ├─ 调用 api.momo('pack')        — 先存档                               │
│     ├─ 调用 api.clearLock()         — 清注入锁                             │
│     ├─ 调用 api.edit(userIndex, txt, false)  — 截断                       │
│     ├─ 调用 api.inject(injectMsg)   — 注入新消息                           │
│     └─ 启动轮询等待 AI 回复                                                │
│                                                                             │
│  ② API层 (core.js: api.edit / api.inject)                                 │
│     ├─ fetch POST /api/edit                                                │
│     └─ fetch POST /api/inject                                              │
│     【错误边界在这里】                                                      │
│     ├─ fetch 网络错误 → 抛出 TypeError → saveEdit.catch 显示「网络错误」   │
│     ├─ HTTP 错误(4xx/5xx) → 抛出 Error → saveEdit.catch 显示「网络错误」   │
│     └─ 业务错误({ok:false, error:...}) → 业务代码检查 res.ok 显示业务错误  │
│     ⚠️  P1问题⚠️: api.post 在 !r.ok 时直接 throw，不尝试读取响应体        │
│        所以 HTTP 500 的 {ok:false, error:"数据库锁"} 会被丢弃              │
│                                                                             │
│  ③ HTTP服务器 (edit-web.py: Handler.do_POST)                              │
│     ├─ [GET /api/ping] → 直接响应, 不经过路由                              │
│     ├─ [/api/edit] → router.post → action='edit' → _handle_api('edit')    │
│     └─ [/api/inject] → router.post → action='inject' → _handle_api('inject')│
│                                                                             │
│     _handle_api 的错误边界:                                                 │
│     ├─ try: 解析 body → 分发 action → 执行 → _send_json(result)           │
│     └─ except: print traceback → _send_json({ok:false, error: err_msg})   │
│     ✅ 统一 try-catch 覆盖所有 action                                       │
│     ⚠️  严重问题⚠️: 对于 Permission denied, 代码做了特殊处理,               │
│         只截取 err.split(':')[-1] 作为友好信息, 但 `err` 可能包含敏感信息  │
│                                                                             │
│  ④ 截断逻辑 (edit_message)                                                │
│     ├─ 读 JSONL → 定位用户消息 → 校验 ⋯                                    │
│     ⚠️  P0问题⚠️: 写盘前没有原子写入                                       │
│     ├─ BACKUP_DIR 写备份 → session_file 写截断内容                         │
│     └─ 返回 {ok:true, truncated: N}                                       │
│     错误分支:                                                               │
│     ├─ user_index 越界 → {ok:false, error:"用户消息索引 #N 无效"}          │
│     ├─ 二重验证失败 → {ok:false, error:"⛔ 二重验证失败: ..."}             │
│     ├─ 保险线触发 → {ok:false, error:"⛔ 保险线(>50% 截断量异常): ..."}    │
│     └─ 安全铁律触发 → {ok:false, error:"⛔ 安全铁律: ..."}                 │
│     ✅ 所有错误路径都返回统一的 {ok:false} 格式                             │
│                                                                             │
│  ⑤ 注入逻辑 (inject_via_websocket)                                        │
│     ├─ 检查 lock 文件 (INJECT_LOCK_FILE, TTL=20s)                          │
│     ⚠️  P0问题⚠️: subprocess.Popen 异步启动后立即 _cleanup_lock()          │
│     ├─ subprocess.Popen(["bun", "inject-helper.mjs", sk, msg], ...)        │
│     └─ 立即返回 {ok:true} (fire-and-forget)                                │
│     错误分支:                                                               │
│     ├─ lock 未过期 → Exception("安全限制：上一轮已注入过...")               │
│     ├─ helper.mjs 不存在 → Exception("inject-helper.mjs not found")        │
│     ├─ TimeoutExpired → Exception("注入超时")                               │
│     └─ 其他异常 → Exception(消息)                                          │
│     ✅ 所有错误路线统一 return {ok:true}（见注）                            │
│     ⚠️  注意⚠️: 即使子进程失败, inject_via_websocket 也返回 {ok:true}      │
│        因为 Popen 启动后就 _cleanup_lock() 并返回成功, 不检查子进程结果    │
│        所以前端获得 {ok:true} 不代表消息已经发送到 Gateway！                │
│                                                                             │
│  ⑥ 子进程 (inject-helper.mjs)                                             │
│     ├─ TCP connect → WebSocket 升级 → recv challenge                      │
│     ├─ 连接认证 (Token + deviceId)                                         │
│     ├─ chat.send RPC (fire-and-forget) → process.stdout.write JSON         │
│     └─ setTimeout → process.exit(0)                                        │
│     错误:                                                                   │
│     ├─ 连接失败 → recvFrame timeout → catch → stderr + exit(1)             │
│     ├─ auth 失败 → throw Error("Connect failed") → exit(1)                 │
│     └─ Gateway 关闭 → 任何 sendFrame 后的 recvFrame 超时                   │
│     ⚠️  但 edit-web.py 使用 subprocess.Popen, 不检查返回码                 │
│        所以子进程崩溃 = 静默失败, 前端看到 {ok:true} 但消息未发送           │
│                                                                             │
│  ⑦ Gateway 内部  (外部系统)                                               │
│     ├─ 收到 chat.send RPC                                                  │
│     ├─ 写入 session JSONL                                                  │
│     └─ 触发 AI 回复                                                        │
│     错误:                                                                   │
│     ├─ session_key 无效 → RPC 错误响应 → 但 edit-web.py 不回读             │
│     ├─ token 无效 → 连接被拒绝 → inject-helper exit(1)                      │
│     └─ Gateway crash → 同上                                                │
│                                                                             │
│  ⑧ 异步响应路径 (AI 回复 → 前端)                                          │
│     ├─ Gateway 将响应写入 session JSONL                                     │
│     ├─ 前端轮询 (core.js: _pollTimer, 每3秒):                              │
│     │   └─ fetch /api/session?fresh=1                                      │
│     │     ├─ file snapshot → read_session → group_into_pairs                │
│     │     └─ 对比 pairs 长度 → 变化 → refresh() → renderPage()             │
│     ⚠️  轮询与编辑器直接写 store.pairs 可能冲突                             │
│     └─ 用户看到 AI 回复出现在界面                                            │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────┐
│ 场景 B: 浏览器直接请求静态文件（GET /static/js/core.js）                    │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ① router.py: cp.startswith('/static/') 匹配                               │
│  ② 路径拼接: os.path.join(_THIS_DIR, cp.lstrip('/'))                      │
│     ⚠️  路径安全问题⚠️: 如果 cp='/static/../../../etc/passwd',            │
│         os.path.join会解析到外部路径。                                       │
│         _serve_static_file 只有 try-except, 没有路径穿越检查                  │
│  ③ 文件存在 → 发送 Content-Type  + 文件内容                                │
│  ④ 文件不存在 → 404 {"ok":false,"error":"File not found"}                  │
│     ✅ 至少返回了JSON错误, 不是纯HTML                                        │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

### 错误传播总结表

| 环节 | 异常类型 | 是否捕获 | 返回格式 | 前端的感知 |
|------|---------|---------|---------|-----------|
| 浏览器 fetch | 网络断开 | cors/TypeError | JS异常 | `catch` 显示"网络错误: ..." |
| 浏览器 fetch | HTTP 5xx | `!r.ok` | throw Error | `catch` 显示"网络错误: API 500" |
| HTTP服务器 | JSON解析失败 | `_handle_api` try/except | {ok:false, error:...} | 显示业务错误消息 |
| HTTP服务器 | 任何异常 | 同上 | {ok:false, error:...} | 显示业务错误消息 |
| edit_message | 校验失败 | 函数内部 if/return | {ok:false, error:...} | 显示业务错误消息 |
| inject_via_websocket | 锁/路径/超时 | 函数内部 try/except | {ok:true} (错误也在内部转换为Exception) | ⚠️ {ok:true} 显示成功 |
| inject-helper.mjs | 连接失败 | catch → exit(1) | 不返回（静默） | ⚠️ {ok:true} 轮询永远等不到回复 |
| inject-helper.mjs | Gateway拒绝 | catch → exit(1) | 不返回（静默） | ⚠️ 同上 |
| 轮询 | fetch任何错误 | catch(e){} | 静默 | 轮询停止不更新界面 |

**关键结论**: 注入路径（`inject_via_websocket`）的错误回传机制是单向的 — 子进程的错误不会通过 Popen 的 stdout 被父进程读取，因为父进程使用 `Popen`（不等待）而不是 `run`。这导致前端永远收到 `{ok:true}`，即使注入实际上失败了。用户看到「已截断并发送」的状态，但 AI 永远不会回复，用户不知道为什么。

---

## 5. 其他重要发现

### 5.1 备份策略
- **现有备份**: 96份预编辑备份 (`pre-edit.YYYYMMDD_HHMMSS.jsonl`) 在 `BACKUP_DIR`
- **机制**: 每次 `edit_message` 执行前都会做备份（写完整 JSONL 到 backup 目录）
- **无统一GC**: 备份文件无限增长，没有自动清理策略
- **缺失**: 没有备份索引，搜索备份必须全量扫描所有 JSONL 文件（`_search_backups` 就是这样做的）
- **建议**: 添加备份 TTL（如30天），或按备份量（保留最近100份）

### 5.2 CORS/OPTIONS
- 当前 `Access-Control-Allow-Origin: *` 只在 `_send_json` 中设置
- `OPTIONS` 预检请求完全没有处理 → 跨域部署时 POST 请求失败
- 静态文件响应中没有 CORS 头
- HTTPS 使用自签名证书，浏览器会阻止 `fetch` 到 HTTPS 端点

### 5.3 配置优先级链
```
环境变量  >  editor-config.json  >  openclaw.json(自动发现)  >  硬编码后备
  │              │                       │
GATEWAY_PORT   GATEWAY_PORT            gateway.port           (无后备 → 启动报错)
EDITOR_PORT    EDITOR_PORT             webchat.port           (无后备 → 启动报错)
GATEWAY_TOKEN  GATEWAY_TOKEN           gateway.auth.token     (空字符串后备)
DATA_DIR       DATA_DIR                sessions/自动发现       (无后备 → 启动报错)
WORKSPACE      WORKSPACE               agents.defaults.workspace (无后备 → 启动报错)
```
配置校验在启动时执行，缺失 = `sys.exit(1)` ✅。但 `/tmp` 路径、`bun` 二进制路径、`openclaw.json` 中的硬编码路径不在配置管理范围内。

### 5.4 线程安全
- `ThreadingHTTPServer` 多线程并发处理
- **INJECT_LOCK_FILE** 文件锁（`_cleanup_lock` 在多线程下存在竞态）
- **store.pairs** 前端多 async 上下文的共享状态
- **backup_dir** 文件写入（多个编辑请求同时备份可能冲突）
- **no logger lock**: `print(..., file=sys.stderr)` 在多线程下输出可能交错

### 5.5 前端JS文件独立性
| 文件 | 行数 | 依赖关系 |
|------|------|---------|
| core.js | ~200 | 定义 api, store, toast, refresh; 被所有其他JS引用 |
| editor.js | ~200 | 依赖: api, store, refresh, renderPage, escapeHtml, toast |
| momo.js | ~250 | 依赖: api, escapeHtml, refresh |
| dashboard.js | ~150 | 依赖: api, updateContextDisplay |
| file-browser.js | ~450 | 依赖: api, escapeHtml |
| render.js | ~350 | 依赖: escapeHtml, renderMarkdown |
| cache-monitor.js | ~200 | 独立组件 |
| components.js | ~150 | 依赖: CL 注册系统 |
| awake.js | ~150 | 依赖: api, toast |
| subagent.js | ~120 | 依赖: api |
| app.js | ~50 | 框架核心 |
| **总计** | ~2972 | **全局耦合（无模块化）** |

---

## 6. 各维度评分

| 维度 | 评分 | 主要扣分项 |
|------|------|-----------|
| **架构耦合度** | 4/10 | edit-web.py 3925行单体；handlers/ 目录为空骨架；双轨过渡代码重复 |
| **错误边界** | 5/10 | HTTP层统一try-catch ✅；注入路径静默失败 ⚠️；前端不区分错误类型 |
| **异步注入模型** | 3/10 | Popen fire-and-forget 不检查结果；锁竞争；子进程错误不回传 |
| **前端错误处理** | 3/10 | api.get/post 不解析错误body；轮询静默吃异常；用户看到"成功"实为失败 |
| **全局状态管理** | 6/10 | 配置发现系统完善但硬编码路径散落；前端store无mutation事件 |
| **备份策略** | 6/10 | 有自动备份但无GC；搜索需要全量扫描 |
| **CORS/OPTIONS** | 2/10 | 无OPTIONS处理器；HTTPS自签名 |
| **总体** | 4.2/10 | 核心功能稳定运行中，但存在多处P0级风险需要立即修复 |

---

## 附录：审计方法

- 手动代码审查（read 全部源文件）
- 文本树分析（find + wc -l 统计代码量）
- 架构图使用 ASCII art 手工绘制
- 错误路径追踪使用源码级别的 control flow 分析
- 所有 P0 问题均可在源码中找到对应的代码行（未列出具体行号以保持报告简洁，审计人员可快速定位）
