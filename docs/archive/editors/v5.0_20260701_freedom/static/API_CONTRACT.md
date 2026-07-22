# 轻如烟编辑器 API 接口契约

> 版本: v5.0
> 更新时间: 2026-07-01
> 所有 API 基路径: `http://127.0.0.1:{EDITOR_PORT}`
> 响应格式: 全部 JSON (`Content-Type: application/json; charset=utf-8`)
> 编码: 支持 Gzip 压缩（当 Accept-Encoding 包含 gzip 且响应 > 512 字节时）
> CORS: 所有端点设置 `Access-Control-Allow-Origin: *`

---

## 目录

### GET 端点
| # | 端点 | 说明 | 代码位置 |
|---|------|------|----------|
| 1 | `/` | 编辑器主页 | `router.py` `get` |
| 2 | `/api/status` | 会话上下文用量统计 | `system_handler.py` `handle_usage_status` |
| 3 | `/api/cache-stats` | 缓存命中统计 | `system_handler.py` `handle_cache_stats` |
| 4 | `/api/version` | 版本信息 | `system_handler.py` `handle_version_info` |
| 5 | `/api/list-sessions` | 列出所有会话 | `router.py` → `list_all_sessions` |
| 6 | `/api/system-health` | 系统健康状态 | `router.py` → `_system_health` |
| 7 | `/api/switch-session?key=` | 切换当前会话 | `router.py` → `set_active_session_key` + `handle_get_session_data` |
| 8 | `/api/delete-session?key=&sessionKey=` | 删除会话 | `session_handler.py` `handle_delete_session` |
| 9 | `/api/session?key=` | 获取会话数据 | `session_handler.py` `handle_get_session_data` |
| 10 | `/api/session-rpc` | RPC 获取会话消息（不走文件） | `session_handler.py` `handle_session_rpc` |
| 11 | `/api/digestion-status` | 消化循环状态 | `router.py` → `_digestion_status` |
| 12 | `/api/digestion-skill` | 监控栏状态 | `router.py` → `_digestion_skill_status` |
| 13 | `/api/digestion-history` | 消化循环历史 | `router.py` → `_digestion_history` |
| 14 | `/api/backlog` | 待办清单 | `router.py` → `_backlog_status` |
| 15 | `/api/backup-stale` | 备份过时检查 | `router.py` → `_backup_stale_status` |
| 16 | `/api/thinking-status` | 思考模式状态 | `router.py` → `_thinking_status` |
| 17 | `/api/weaponry-toggle` | 武器库开关状态 | `router.py` → `_weaponry_toggle_status` |
| 18 | `/api/plugin-health` | 插件注入状态 | `router.py` → `_plugin_health` |
| 19 | `/api/last-injection` | 最近插件注入 | `router.py` → `_last_injection` |
| 20 | `/api/last-processing` | 最近静默处理 | `router.py` → `_last_processing` |
| 21 | `/api/subagent-history` | 子代理执行历史 | `router.py` → `_get_subagent_history` |
| 22 | `/api/tb-files?folder=` | 文件浏览（列文件） | `file_handler.py` `handle_tb_files` |
| 23 | `/api/tb-read-file?path=&pw=` | 读取文件内容 | `file_handler.py` `handle_tb_read_file` |
| 24 | `/api/list-files?folder=&path=` | 列出文件夹 .md 文件 | `file_handler.py` `handle_list_files` |
| 25 | `/api/browse-dirs` | 浏览根目录文件夹 | `file_handler.py` `handle_browse_dirs` |
| 26 | `/api/quickcheck` | 快速健康检查 | `system_handler.py` `handle_quickcheck` |
| 27 | `/api/secretary-log` | 秘书观察日志 | `helper_handler.py` `handle_secretary_log` |
| 28 | `/api/facts-stale` | 事实过时检查 | `helper_handler.py` `handle_facts_stale_check` |
| 29 | `/api/reminders` | 提醒列表 | `helper_handler.py` `handle_reminders` |
| 30 | `/api/backups` | 列出截断备份 | `session_handler.py` `handle_list_backups` |
| 31 | `/api/subagents` | 列出子代理 | `system_handler.py` `handle_list_subagents` |
| 32 | `/api/memory-files` | 列出记忆文件 | `helper_handler.py` `handle_memory_file_list` |
| 33 | `/api/memory-file?name=` | 读取记忆文件 | `helper_handler.py` `handle_memory_file_get` |
| 34 | `/api/awake-questions/list` | 唤醒题库列表 | `awake_handler.py` `handle_awake_list` |
| 35 | `/api/encrypt...` | 加密相关（子路径） | `crypto_handler.py` `handle_encrypt` |
| 36 | `/paper-annotated.html` | 论文标注页面 | `router.py` 内联 |
| 37 | `/static/*` | 静态文件服务 | `router.py` `_serve_static_file` |

### POST 端点
| # | 端点 | 说明 | 代码位置 |
|---|------|------|----------|
| 38 | `/api/ping` | 基础连通性测试 | `edit-web.py` `do_POST` |
| 39 | `/api/abort` | 停止 AI 思考 | `inject_handler.py` `handle_abort` |
| 40 | `/api/restart-http` | 重启 HTTP 服务器 | `inject_handler.py` `handle_restart_http` |
| 41 | `/api/pet-me` | 静默处理（撸撸） | `momo_handler.py` `handle_pet_me` |
| 42 | `/api/trim-session` | 裁剪会话 | `session_handler.py` `handle_trim_session` |
| 43 | `/api/thinking-toggle` | 切换思考模式 | `system_handler.py` `handle_thinking_toggle` |
| 44 | `/api/weaponry-toggle` | 切换武器库开关 | `system_handler.py` `handle_weaponry_toggle` |
| 45 | `/api/inject` | 注入消息 | `inject_handler.py` `handle_inject` |
| 46 | `/api/edit` | 截断编辑消息 | `inject_handler.py` `handle_edit` |
| 47 | `/api/clear-inject-lock` | 清除注入锁 | `inject_handler.py` `handle_clear_lock` |
| 48 | `/api/pulse` | 保活脉冲 | `inject_handler.py` `handle_pulse` |
| 49 | `/api/momo` | 摸摸协议主入口 | `momo_handler.py` `handle_momo` |
| 50 | `/api/spawn-subagent` | Spawn 子代理 | `inject_handler.py` `handle_spawn_subagent` |
| 51 | `/api/auth-subagent` | 授权子代理设备 | `inject_handler.py` `handle_auth_subagent` |
| 52 | `/api/exec-subagent` | 执行子代理 | `inject_handler.py` `handle_exec_subagent` |
| 53 | `/api/reminders` | 提醒管理 | `helper_handler.py` `handle_reminders` |
| 54 | `/api/memory-file` | 保存记忆文件 | `helper_handler.py` `handle_memory_file_save` |
| 55 | `/api/awake-questions/list` | 唤醒题库列表（POST） | `awake_handler.py` `handle_awake_list` |
| 56 | `/api/awake-questions/save` | 保存唤醒题库 | `awake_handler.py` `handle_awake_save` |
| 57 | `/api/tts` | 文本转语音 | `awake_handler.py` `handle_tts` |
| 58 | `/api/encrypt` | 加密文件夹 | `crypto_handler.py` `handle_encrypt` |
| 59 | `/api/tb-save-file` | 保存文件 | `file_handler.py` `handle_tb_save_file` |
| 60 | `/api/tb-create-file` | 创建文件/目录 | `file_handler.py` `handle_tb_create_file` |
| 61 | `/api/tb-rename-file` | 重命名/移动文件 | `file_handler.py` `handle_tb_rename_file` |
| 62 | `/api/tb-delete-file` | 删除文件/目录 | `file_handler.py` `handle_tb_delete_file` |

### WebSocket / 内部端点
| # | 端点 | 说明 |
|---|------|------|
| — | WebSocket (Gateway) | 通过 `inject-helper.mjs` 调用 Gateway RPC `chat.send` |

---

## 详细 API 说明

---

## 1. `GET /` — 编辑器主页

读取 `static/index.html` 并返回。支持 gzip 压缩。

**代码位置**: `router.py` `get()` → `_get_html_page()`

**参数**: 无

**响应**: `text/html; charset=utf-8`
- `Cache-Control: no-cache`
- 支持 `Accept-Encoding: gzip` 压缩

**错误响应**: `500 {"ok": false}`（当 `_get_html_page` 不可用时）

---

## 2. `GET /api/status` — 会话上下文用量统计

**代码位置**: `system_handler.py` `handle_usage_status`

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "totalTokens": 67150,
  "contextTokens": 1000000,
  "inputTokens": 35000,
  "outputTokens": 32150,
  "cacheRead": 5000,
  "compactionCount": 2,
  "percent": 7,
  "trimCount": 3
}
```

**字段说明：**
| 字段 | 类型 | 说明 |
|------|------|------|
| totalTokens | int | 当前会话总 token 数 |
| contextTokens | int | 模型支持的最大上下文窗口（从配置文件读取） |
| inputTokens | int | 输入 token |
| outputTokens | int | 输出 token |
| cacheRead | int | 缓存读取 token |
| compactionCount | int | 压缩次数 |
| percent | int | 上下文已用百分比 `(total/context × 100)` |
| trimCount | int | 截断操作累计次数 |

**错误响应：** `{"ok": false, "error": "..."}`

---

## 3. `GET /api/cache-stats` — 缓存命中统计 v2

**代码位置**: `system_handler.py` `handle_cache_stats`

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "tokens_decoded": 120000,
  "tokens_encoded": 25000,
  "tokens_saved": 95000,
  "efficiency_pct": 79.2,
  "cache_hits": 8,
  "cache_misses": 3,
  ...
}
```

**错误响应：** `{"ok": false, "error": "..."}`

---

## 4. `GET /api/version` — 版本信息

**代码位置**: `system_handler.py` `handle_version_info`
**数据源**: `utils/version.py`

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "version": "v5.0",
  "date": "2026-07-01",
  "full": "v5.0「自由王国 (Freedom First)」— 2026-07-01",
  "deliver": "轻如烟"
}
```

---

## 5. `GET /api/list-sessions` — 列出所有会话

**代码位置**: `router.py` → `list_all_sessions()`（位于 `edit-web.py`，委托 `utils/session`）

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "sessions": [
    {"key": "agent:main:main", "label": "主会话", "updated": "...", "tokenCount": 50000},
    {"key": "agent:main:subagent:xxx", "label": "子代理", "updated": "...", "tokenCount": 2000}
  ]
}
```

**错误响应：** `{"ok": false, "error": "..."}`
- `404 {}`（如果 `list_all_sessions` 不可用）

---

## 6. `GET /api/system-health` — 系统健康状态

**代码位置**: `router.py` → `_system_health()`（委托 `utils/status_reports`）

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "config_exists": true,
  "session_dir_exists": true,
  "gateway_running": true,
  ...
}
```

---

## 7. `GET /api/switch-session?key=<session_key>` — 切换当前会话

**代码位置**: `router.py` `get()` 内联逻辑

**参数：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| key | string | 否 | 目标会话 key。不传则设为 `None`（默认主会话） |

**响应**: 同 `GET /api/session`（`handle_get_session_data` 返回值）

---

## 8. `GET /api/delete-session?key=<session_key>&sessionKey=<session_key>` — 删除会话

**代码位置**: `session_handler.py` `handle_delete_session`

**参数：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| key | string | 是（与 sessionKey 二选一） | 要删除的会话 key |
| sessionKey | string | 是（与 key 二选一） | 同上，兼容别名 |

**流程：** 改名 `.jsonl` → `.deleted.时间戳`，从 `sessions.json` 中移除，如果删除的是当前激活会话则重置。

**响应示例：**
```json
{
  "ok": true,
  "deleted": "agent:main:subagent:xxx"
}
```

**错误响应：**
- `400` `{"ok": false, "error": "missing sessionKey"}`
- `404` `{"ok": false, "error": "session key not found"}`

---

## 9. `GET /api/session?key=<session_key>` — 获取会话数据

**代码位置**: `session_handler.py` `handle_get_session_data`

**参数：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| key | string | 否 | 临时切换到此 key 读取；不传则读取当前激活会话 |

**响应示例：**
```json
{
  "sessionFile": "/path/to/sessions/agent:main:main.jsonl",
  "sessionKey": "agent:main:main",
  "total": 120,
  "userCount": 45,
  "messageCount": 120,
  "pairs": [
    {
      "userIndex": 0,
      "user": {"role": "user", "content": "你好"},
      "assistant": {"role": "assistant", "content": "你好！"}
    }
  ],
  "info": {
    "host": "127.0.0.1",
    "port": 18888,
    "sessionFile": "/path/to/sessions/agent:main:main.jsonl",
    "dataDir": "/path/to/sessions"
  }
}
```

**字段说明：**
| 字段 | 类型 | 说明 |
|------|------|------|
| pairs | array | user-assistant 消息对，**倒序**（最新在前） |
| pairs[].userIndex | int | 用户消息序号（从 0 开始，用于编辑截断） |
| info.port | int | Gateway 端口 |

---

## 10. `GET /api/session-rpc` — RPC 获取会话消息

**代码位置**: `session_handler.py` `handle_session_rpc`

**参数**: 无（通过环境变量 `SESSION_KEY` 传给子进程）

**流程**: 调用 `gateway-history.js` 通过 Gateway RPC (`chat.history`) 获取原始消息。

**响应示例：**
```json
{
  "ok": true,
  "from_rpc": true,
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "count": 120
}
```

**错误响应：** `{"ok": false, "error": "rpc timeout|rpc error: ..."}`

---

## 11. `GET /api/digestion-status` — 消化循环状态

**代码位置**: `router.py` → `_digestion_status()`（委托 `utils/status_reports`）

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "last_digest_time": "18:30",
  "last_digest_date": "2026-07-01",
  "interval_minutes": 30,
  "status": "active",
  ...
}
```

---

## 12. `GET /api/digestion-skill` — 监控栏状态

**代码位置**: `router.py` → `_digestion_skill_status()`（委托 `utils/status_reports`）

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "plugin_injected": true,
  "last_inject_time": "...",
  "hooks_active": 3,
  ...
}
```

---

## 13. `GET /api/digestion-history` — 消化循环历史

**代码位置**: `router.py` → `_digestion_history()`（委托 `utils/status_reports`）

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "history": [
    {"time": "2026-07-01 18:00", "status": "ok"},
    {"time": "2026-07-01 17:30", "status": "ok"}
  ]
}
```

---

## 14. `GET /api/backlog` — 待办清单

**代码位置**: `router.py` → `_backlog_status()`（委托 `utils/status_reports`）

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "items": [
    {"text": "优化 xyz", "done": false}
  ],
  "count": 5
}
```

---

## 15. `GET /api/backup-stale` — 备份过时检查

**代码位置**: `router.py` → `_backup_stale_status()`（委托 `utils/status_reports`）

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "stale": false,
  "last_backup": "2026-07-01 12:00",
  ...
}
```

---

## 16. `GET /api/thinking-status` — 思考模式状态

**代码位置**: `router.py` → `_thinking_status()`（委托 `utils/status_reports`）

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "thinking_level": "high",
  ...
}
```

---

## 17. `GET /api/weaponry-toggle` — 武器库开关状态

**代码位置**: `router.py` → `_weaponry_toggle_status()`（委托 `utils/status_reports`）

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "weaponry_enabled": true,
  ...
}
```

---

## 18. `GET /api/plugin-health` — 插件注入状态

**代码位置**: `router.py` → `_plugin_health()`（委托 `utils/status_reports`）

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "plugin_injected": true,
  "last_plugin_run": "...",
  "plugin_ran": true,
  ...
}
```

---

## 19. `GET /api/last-injection` — 最近插件注入

**代码位置**: `router.py` → `_last_injection()`（委托 `utils/status_reports`）

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "last_injection": "...",
  "last_injection_body": "...",
  ...
}
```

---

## 20. `GET /api/last-processing` — 最近静默处理

**代码位置**: `router.py` → `_last_processing()`（委托 `utils/status_reports`）

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "last_processing": "2026-07-01 17:00",
  ...
}
```

---

## 21. `GET /api/subagent-history` — 子代理执行历史

**代码位置**: `router.py` → `_get_subagent_history()`（委托 `utils/subagent`）

**参数**: 无（默认返回最近 20 条）

**响应示例：**
```json
{
  "ok": true,
  "history": [
    {
      "time": "...",
      "model": "deepseek-chat",
      "task": "...",
      "status": "completed"
    }
  ]
}
```

---

## 22. `GET /api/tb-files?folder=<path>` — 文件浏览

**代码位置**: `file_handler.py` `handle_tb_files`

**参数：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| folder | string | 是 | 相对于 `BROWSE_ROOT` 的文件夹路径 |

**响应示例：**
```json
{
  "ok": true,
  "folder": "小说/武侠",
  "files": ["第一章.md", "第二章.md"],
  "file_count": 2
}
```

**错误响应：** `{"ok": false, "error": "需要 folder 参数|..."}`

---

## 23. `GET /api/tb-read-file?path=<abs_path>&pw=<password>` — 读取文件内容

**代码位置**: `file_handler.py` `handle_tb_read_file`

**参数：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| path | string | 是 | 文件绝对路径 |
| pw | string | 否 | AES 加密密码（LSE 格式加密文件时提供） |

**支持格式：**
- 纯文本 (.md, .txt, .json, .py 等)
- Office 文档 (.docx) — 自动提取文本
- AES 加密文件（.md 等，以 `LSE` 为魔数开头）

**响应示例（纯文本）：**
```json
{
  "ok": true,
  "content": "文件内容..."
}
```

**响应示例（docx）：**
```json
{
  "ok": true,
  "content": "文本内容...",
  "note": "docx 文本提取，格式可能简化"
}
```

**错误响应：** `{"ok": false, "error": "文件不存在|需要 path 参数|..."}`

---

## 24. `GET /api/list-files?folder=<name>&path=<abs_path>` — 列出文件夹文件

**代码位置**: `file_handler.py` `handle_list_files`

**参数：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| folder | string | 二选一 | 相对于 `LIGHT_SMOKE_DIR` 的文件夹名 |
| path | string | 二选一 | 绝对路径 |

**响应示例：**
```json
{
  "ok": true,
  "folder": "memory",
  "folder_path": "/path/to/memory",
  "files": ["2026-07-01.md", "facts.dict.md"],
  "file_count": 2,
  "items": ["subdir1", "subdir2"]
}
```

**items**: 子目录名列表

---

## 25. `GET /api/browse-dirs` — 浏览根目录文件夹

**代码位置**: `file_handler.py` `handle_browse_dirs`

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "root": "/vol1/@team/qh团队",
  "items": [
    {"name": "小说", "path": "小说", "is_dir": true},
    {"name": "脚本", "path": "脚本", "is_dir": true}
  ]
}
```

由 `utils/tb_handler.browse_root_dirs()` 生成。

---

## 26. `GET /api/quickcheck` — 快速健康检查

**代码位置**: `system_handler.py` `handle_quickcheck`

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "timestamp": "17:44:00",
  "editor": "alive",
  "cron": "active(3)",
  "inject": "ok",
  "memory": "2026-07-01.md OK(12K)",
  "lastDigest": "5min ago"
}
```

**字段说明：**
| 字段 | 说明 |
|------|------|
| cron | `active(N)` — 活跃定时任务数；`missing` — 配置文件丢失 |
| inject | `ok` 或 `locked(Ns)` — 注入锁状态 |
| memory | 今日记忆文件状态，含大小 |
| lastDigest | 距上次消化循环的时间 |

---

## 27. `GET /api/secretary-log` — 秘书观察日志

**代码位置**: `helper_handler.py` `handle_secretary_log`

**参数**: 无

**读取文件**: `<LIGHT_SMOKE_DIR>/memory/秘书观察.log`

**响应示例：**
```json
{
  "ok": true,
  "total": 150,
  "recent": [
    "[2026-07-01 17:00] 观察到文件 xxx.md 变更",
    "[2026-07-01 16:30] 提醒: 记得喝水"
  ]
}
```

---

## 28. `GET /api/facts-stale` — 事实过时检查

**代码位置**: `helper_handler.py` `handle_facts_stale_check`

**参数**: 无

**流程**: 运行 `<LIGHT_SMOKE_DIR>/scripts/check-facts-stale.sh --json` + 断言新鲜度检查

**响应示例：**
```json
{
  "ok": true,
  "stale": false,
  "source_files": [...],
  "dep_files": [...],
  "assertions": {
    "ok": true,
    "count": 5,
    "msg": "断言5条含置信度"
  }
}
```

---

## 29. `GET/POST /api/reminders` — 提醒系统

**代码位置**: `helper_handler.py` `handle_reminders`

### GET — 列出待办提醒

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "reminders": [
    {"id": "uuid", "text": "喝水", "done": false, "assignee": "", "trigger_hint": ""}
  ],
  "count": 3
}
```

### POST — 管理提醒

**请求体（JSON）：**

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| action | string | 是 | `"add"` / `"done"` / `"clear_done"` |
| text | string | add 时必需 | 提醒文本 |
| assignee | string | 否 | 负责人 |
| trigger_hint | string | 否 | 触发提示 |
| id | string | done 时必需 | 提醒 ID |

**响应示例（add）：**
```json
{"ok": true, "reminder": {"id": "uuid", "text": "喝水", "done": false}}
```

**响应示例（done）：**
```json
{"ok": true}
```

**响应示例（clear_done）：**
```json
{"ok": true, "remaining": 2}
```

---

## 30. `GET /api/backups` — 列出截断备份

**代码位置**: `session_handler.py` `handle_list_backups`

**参数**: 无

**读取目录**: `BACKUP_DIR`（`pre-edit.*.jsonl` 文件）

**响应示例：**
```json
{
  "backups": [
    {
      "filename": "pre-edit.20260701_120000.jsonl",
      "timestamp": "2026-07-01 12:00:00",
      "size": 10240,
      "preview": "{\"type\":\"message\", ...}"
    }
  ]
}
```

---

## 31. `GET /api/subagents` — 列出子代理

**代码位置**: `system_handler.py` `handle_list_subagents`

**参数**: 无

**数据源**: `sessions.json`（搜索 `subagent` 键）

**响应示例：**
```json
{
  "ok": true,
  "active": [
    {
      "key": "subagent:xxx",
      "model": "GLM-Z1-Flash",
      "updated": "5m ago",
      "age_ms": 300000,
      "state": "running",
      "task": "分析数据...",
      "result": "分析结果预览...",
      "lines": 45,
      "sessionFile": "/path/xxx.jsonl"
    }
  ],
  "recent": [...]
}
```

**字段说明：**
- `active`: 最近 10 分钟内有更新的子代理
- `recent`: 更早的子代理
- 各列表最多 20/10 条

---

## 32. `GET /api/memory-files` — 列出记忆文件

**代码位置**: `helper_handler.py` `handle_memory_file_list`

**参数**: 无

**读取目录**: `<LIGHT_SMOKE_DIR>/memory/`

**响应示例：**
```json
{
  "ok": true,
  "files": [
    {"name": "2026-07-01.md", "size": "12.0KB", "modified": "07-01 17:00"},
    {"name": "facts.dict.md", "size": "8.5KB", "modified": "07-01 16:00"}
  ]
}
```

---

## 33. `GET /api/memory-file?name=<filename.md>` — 读取记忆文件

**代码位置**: `helper_handler.py` `handle_memory_file_get`

**参数：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| name | string | 是 | 文件名（仅 `.md` 后缀，自动限制在 `memory/` 目录） |

**安全约束：**
- 文件名经过 `os.path.basename()` 处理，防止目录穿越
- 仅允许 `.md` 后缀

**响应示例：**
```json
{
  "ok": true,
  "content": "# 记忆内容...",
  "path": "/path/to/memory/2026-07-01.md",
  "size": 12000
}
```

**错误响应：**
- `{"ok": false, "error": "missing ?name= 参数"}`
- `{"ok": false, "error": "只允许 .md 文件"}`
- `{"ok": false, "error": "文件不存在: xxx"}`

---

## 34. `GET /api/awake-questions/list` — 唤醒题库列表

**代码位置**: `awake_handler.py` `handle_awake_list`

**参数**: 无

**读取文件**: `<scripts>/唤醒题库.md`

**响应示例：**
```json
{
  "ok": true,
  "questions": ["q01 - 今天过得怎么样？", "q02 - 有什么想聊的？"],
  "total": 15,
  "file_content": "# 唤醒题库...\nq01 - ...\n"
}
```

---

## 35. `GET /api/encrypt...` — 加密相关（前缀匹配）

**代码位置**: `crypto_handler.py` `handle_encrypt`

**匹配规则**: 路径以 `/api/encrypt` 开头，包括 `/api/encrypt` 和 `/api/encrypt-status`。

**参数（Query String）：**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| folder | string | 否 | 文件夹名，默认 `"encrypted"` |

> **注意**: GET 方式调用会尝试读取请求体，可能产生异常。加密操作推荐使用 POST。

---

## 36. `GET /paper-annotated.html` — 论文标注页面

**代码位置**: `router.py` `get()` 内联

**参数**: 无

**查找路径**（按顺序）：
1. `<LIGHT_SMOKE_DIR>/../../牛马工作/沈总论文/论文_AI高频词标注.html`
2. `/vol1/@team/qh团队/QH/AI专用/牛马工作/沈总论文/论文_AI高频词标注.html`

**响应**: `text/html; charset=utf-8`

**错误响应：** `{"ok": false, "error": "论文文件不存在"}`

---

## 37. `GET /static/*` — 静态文件服务

**代码位置**: `router.py` `get()` 内联

**路径**: `<SCRIPT_DIR>/static/<path>`（从 `_THIS_DIR` 拼接）

**MIME 类型映射：**
| 扩展名 | Content-Type |
|--------|-------------|
| `.js` | `application/javascript; charset=utf-8` |
| `.css` | `text/css; charset=utf-8` |
| `.html` | `text/html; charset=utf-8` |
| `.png` | `image/png` |
| `.jpg` | `image/jpeg` |
| `.svg` | `image/svg+xml` |
| 其他 | `application/octet-stream` |

**错误响应：** `404 {"ok": false, "error": "File not found"}`

---

## 38. `POST /api/ping` — 基础连通性测试

**代码位置**: `edit-web.py` `Handler.do_POST()` 内联

**参数**: 无

**响应示例：**
```json
{
  "ok": true,
  "identity": "qh",
  "gateway_port": 18888,
  "time": 1719842640.123,
  "host": "hostname"
}
```

---

## 39. `POST /api/abort` — 停止 AI 思考

**代码位置**: `inject_handler.py` `handle_abort`

**参数**: 无

**流程**: 调用 `inject-helper.mjs` 发送 `chat.abort` RPC

**响应示例：**
```json
{"ok": true}
```

**响应（timeout）：**
```json
{"ok": true, "note": "abort timeout (likely succeeded)"}
```

---

## 40. `POST /api/restart-http` — 重启 HTTP 服务器

**代码位置**: `inject_handler.py` `handle_restart_http`

**参数**: 无

**流程**:
1. 发送 `200` 响应
2. 等待 1 秒
3. 向当前进程发送 `SIGKILL`
4. 用 `exec python3` 启动新进程

**响应示例：**
```json
{"ok": true, "note": "HTTP 服务器正在重启..."}
```

---

## 41. `POST /api/pet-me` — 静默处理（撸撸）

**代码位置**: `momo_handler.py` `handle_pet_me`

**参数**: 无

**流程**:
1. 检查 `facts.dict.md` 中 ⏳ 待升格断言
2. 触发备份 (`momo-pack-cli.py`)
3. 写入处理时间戳

**响应示例：**
```json
{
  "ok": true,
  "summary": "⏳待升格: 3条\n知识树已检查\n备份完成"
}
```

---

## 42. `POST /api/trim-session` — 裁剪会话

**代码位置**: `session_handler.py` `handle_trim_session`

**参数**: 无（作用在当前激活会话）

**流程**:
1. 找到最近 3 轮用户消息
2. 保留 `session header (line 0)` + 最后 3 轮（含之后的所有消息）
3. 修复断链的 `parentId`
4. 自动备份至 `BACKUP_DIR`
5. 更新 `trim-counter`

**安全约束**:
- 会话少于 5 行则不裁剪
- 会话不足 4 轮用户消息则不裁剪

**响应示例：**
```json
{
  "ok": true,
  "from_bytes": 500000,
  "to_bytes": 100000,
  "removed_msgs": 80,
  "reduced_pct": 80,
  "kept_rounds": 3,
  "broken_refs_fixed": 2,
  "backup": "pre-trim.20260701_174400.jsonl",
  "note": "Session trimmed. Restart required for changes to take effect."
}
```

**错误响应：**
- `{"ok": false, "error": "Session file not found"}`
- `{"ok": false, "error": "Session too short to trim"}`
- `{"ok": false, "error": "Only N rounds, no trimming needed"}`

---

## 43. `POST /api/thinking-toggle` — 切换思考模式

**代码位置**: `system_handler.py` `handle_thinking_toggle`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| （可选体，实际读取当前 thinkingLevel 自动循环） | — | — | — |

**循环逻辑**: `off` → `medium` → `high` → `off`

**响应示例：**
```json
{
  "ok": true,
  "mode": "medium",
  "previous": "off"
}
```

---

## 44. `POST /api/weaponry-toggle` — 切换武器库开关

**代码位置**: `system_handler.py` `handle_weaponry_toggle`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| enable | bool | 是 | `true` 启用 / `false` 禁用 |

**流程**: 修改 `CRON_JSON`（cron/jobs.json）中名称含"武器库"的任务的 `enabled` 字段

**响应示例：**
```json
{"ok": true, "enabled": true}
```

---

## 45. `POST /api/inject` — 注入消息到当前会话

**代码位置**: `inject_handler.py` `handle_inject`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| message | string | 是 | 要注入的消息内容 |

**流程**:
1. 获取当前会话 key
2. 调用 `inject_via_websocket()` 通过 Gateway WebSocket RPC 发送消息
3. 触发沙漏记忆写入
4. 执行注入锁检查（每用户轮最多 1 次）

**错误示例（权限拒绝）：**
```json
{"ok": false, "error": "无权限: ..."}
```

**错误示例（安全限制）：**
```json
{"ok": false, "error": "安全限制：上一轮已注入过，请在下一轮用户消息后再试"}
```

**超时**: 默认 60 秒（可通过 `INJECT_TIMEOUT` 环境变量设置）

---

## 46. `POST /api/edit` — 截断编辑会话消息

**代码位置**: `inject_handler.py` `handle_edit`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| index | int | 是 | 用户消息序号（从 0 开始，0=最新一轮） |
| text | string | 是 | 要替换的文本（当前仅用于定位，实际执行截断） |
| approved | bool | 否 | 是否获主人授权绕过安全锁，默认 `false` |

**安全约束**:
- 🔒 默认只允许截断最近 `MAX_EDIT_DEPTH=1` 轮
- 🛡️ 保险线：截断超过总行 50% 时拒绝
- 🔒 二重验证：`index` 必须指向 `role=user` 的消息

**流程**:
1. 定位 `index` 处的用户消息
2. 安全检查
3. 备份原文件至 `BACKUP_DIR`
4. 截断：保留 `index` 之前的所有行

**响应示例：**
```json
{
  "ok": true,
  "user_index": 0,
  "truncated": 2,
  "warnings": ["截断 1 轮（距离=4 行）"]
}
```

**错误示例：**
```json
{"ok": false, "error": "⛔ 安全铁律：最多截断最近 1 轮"}
```

---

## 47. `POST /api/clear-inject-lock` — 清除注入锁

**代码位置**: `inject_handler.py` `handle_clear_lock`

**参数**: 无

**响应示例：**
```json
{"ok": true}
```

---

## 48. `POST /api/pulse` — 保活脉冲

**代码位置**: `inject_handler.py` `handle_pulse`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| mode | string | 否 | 脉冲模式（传给 `_send_pulse`） |

**流程**: 委托 `utils/pulse.send_pulse()`，执行保活操作（包括守夜问题检查、日记总结等）

**响应示例：**
```json
{"ok": true, "actions": [...]}
```

---

## 49. `POST /api/momo` — 摸摸协议主入口

**代码位置**: `momo_handler.py` `handle_momo`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| sub_action | string | 是 | 子操作类型（见下方列表） |
| feeling | string | inject_feeling 时必需 | 注入的感觉/消息 |
| query | string | search_backups 时可选 | 搜索关键词 |
| limit | int | 否 | 搜索结果限制，默认 5 |
| password | string | 否 | 解密密码 |
| file | string | 否 | 文件名 |

### sub_action 列表

| sub_action | 说明 | 委托函数 |
|------------|------|----------|
| `pack` | 打包存档/备份 | `_momo_pack()` |
| `inject_feeling` | 注入感觉（绕过锁） | `inject_via_websocket(bypass_lock=True)` |
| `status` | 摸摸状态 | `_momo_status()` |
| `list_backups` | 列出备份 | `handle_list_backups` |
| `restore_backup` | 恢复备份 | `handle_restore_backup` |
| `search_backups` | 搜索备份 | `_search_backups()` |
| `read_facts` | 读取事实字典 | 内联读取 `memory/facts.dict.md` |
| `index_report` | 索引报告 | `_momo_index_report()` |
| `trigger_digest` | 触发消化循环 | `openclaw cron run <id>` |
| `promote_assertions` | 提升待定断言 | `_promote_pending_assertions()` |
| `thinking_on` | 开启思考模式 | `openclaw agent --message "/thinking high"` |
| `thinking_off` | 关闭思考模式 | `openclaw agent --message "/thinking off"` |

**响应示例（pack）：**
```json
{"ok": true, "pack_files": ["xxx.momo"], "total_size": 102400}
```

**响应示例（inject_feeling）：**
```json
{
  "ok": true,
  "_timing": {"get_session": 0.002, "inject": 1.234}
}
```

**响应示例（status）：**
```json
{"ok": true, "momo_files": 3, "last_save": "..."}
```

**响应示例（read_facts）：**
```json
{"ok": true, "content": "# 事实字典...", "size": 5000}
```

**错误示例：**
```json
{"ok": false, "error": "未知摸摸操作: xxx，可用: pack, inject_feeling, ..."}
```

---

## 50. `POST /api/spawn-subagent` — Spawn 子代理

**代码位置**: `inject_handler.py` `handle_spawn_subagent`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| task | string | 是 | 子代理任务描述 |
| model | string | 否 | 模型名，默认 `"GLM-Z1-Flash"` |

**流程**: 委托 `utils/subagent.spawn_subagent_process()`，通过 Gateway RPC 创建子代理会话

**响应示例：**
```json
{"ok": true, "sessionKey": "agent:main:subagent:xxx", "pid": 12345}
```

---

## 51. `POST /api/auth-subagent` — 授权子代理设备

**代码位置**: `inject_handler.py` `handle_auth_subagent`

**参数**: 无

**流程**: 通过 `inject-helper.mjs` 发送 `device.requestApproval` RPC

**响应示例：**
```json
{"ok": true}
```

---

## 52. `POST /api/exec-subagent` — 执行子代理

**代码位置**: `inject_handler.py` `handle_exec_subagent`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| task | string | 是 | 任务描述 |
| model | string | 否 | 模型名，默认 `"deepseek-chat"` |

**响应示例：**
```json
{"ok": true, "result": "...", "elapsed": 5.2}
```

---

## 53. `POST /api/memory-file` — 保存记忆文件

**代码位置**: `helper_handler.py` `handle_memory_file_save`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| name | string | 是 | 文件名（仅 `.md`，自动限制在 `memory/`） |
| content | string | 是 | 文件内容 |

**安全约束：**
- `os.path.basename()` 处理，防止目录穿越
- 仅允许 `.md` 后缀

**响应示例：**
```json
{
  "ok": true,
  "path": "/path/to/memory/my-note.md",
  "size": 500
}
```

---

## 54. `POST /api/awake-questions/save` — 保存唤醒题库

**代码位置**: `awake_handler.py` `handle_awake_save`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| content | string | 是 | 完整题库文件内容 |

**写入文件**: `<scripts>/唤醒题库.md`

**响应示例：**
```json
{"ok": true, "note": "已保存 (1500 bytes)"}
```

---

## 55. `POST /api/tts` — 文本转语音

**代码位置**: `awake_handler.py` `handle_tts`

**引擎**: `edge-tts`（微软 Edge 语音），语音 `zh-CN-XiaoxiaoNeural`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| text | string | 是 | 要转为语音的文本 |

**响应示例：**
```json
{
  "ok": true,
  "audio": "base64...",
  "format": "mp3"
}
```

音频数据为 Base64 编码的 MP3 格式。

---

## 56. `POST /api/encrypt` — 加密文件夹

**代码位置**: `crypto_handler.py` `handle_encrypt`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| folder | string | 否 | 文件夹名，默认 `"encrypted"` |
| password | string | 是 | 加密密码 |
| save_password | bool | 否 | 是否保存密码到保险箱，默认 `false` |

**流程**:
1. 列出目标文件夹下所有 `.md` 文件
2. 对已加密的文件先解密再用新密码重加密
3. 用 XOR 加密写入
4. 清除 `SESSION_DECRYPTED` 状态

**响应示例：**
```json
{
  "ok": true,
  "folder": "/path/to/encrypted",
  "encrypted_count": 5,
  "password_saved": true
}
```

---

## 57. `POST /api/tb-save-file` — 保存文件

**代码位置**: `file_handler.py` `handle_tb_save_file`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| path | string | 是 | 文件绝对路径 |
| content | string | 是 | 文件内容 |

**副作用**:
1. 写入文件
2. 记录保存事件（`SAVE_MONITOR_DIR`）
3. 记录文件变更（`FILE_CHANGE_DIR`）
4. 秘书分析（`secretary_analyze_save`）

**响应示例：**
```json
{"ok": true, "message": "保存成功"}
```

---

## 58. `POST /api/tb-create-file` — 创建文件/目录

**代码位置**: `file_handler.py` `handle_tb_create_file`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| folder | string | 是 | 父文件夹路径 |
| name | string | 是 | 文件/目录名 |
| is_dir | bool | 否 | 是否创建目录，默认 `false` |

**响应示例：**
```json
{"ok": true, "message": "文件已创建", "path": "/path/to/new_file.md"}
```

---

## 59. `POST /api/tb-rename-file` — 重命名/移动文件

**代码位置**: `file_handler.py` `handle_tb_rename_file`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| old_path | string | 是 | 原路径 |
| new_name | string | 是 | 新文件名 |
| new_folder | string | 否 | 目标文件夹（跨目录移动时） |

**响应示例：**
```json
{"ok": true, "message": "文件已重命名", "new_path": "/path/to/new_name.md"}
```

---

## 60. `POST /api/tb-delete-file` — 删除文件/目录

**代码位置**: `file_handler.py` `handle_tb_delete_file`

**请求体（JSON）：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| path | string | 是 | 要删除的文件/目录绝对路径 |

**响应示例：**
```json
{"ok": true, "message": "文件已删除"}
```

---

## 错误码

| 状态码 | 含义 | 说明 |
|--------|------|------|
| 200 | OK | 业务成功或失败（错误信息在 JSON body 中） |
| 400 | Bad Request | 请求参数缺失（如未传 `sessionKey`） |
| 403 | Forbidden | 越权访问（文件夹路径不在 `BROWSE_ROOT` 内） |
| 404 | Not Found | 路由未匹配或资源不存在 |
| 500 | Internal Server Error | 服务端未捕获异常 |

**错误响应统一格式：**
```json
{"ok": false, "error": "具体错误消息"}
```

**注意**：大多数 POST 端点即使业务失败也返回 HTTP 200，错误信息包含在 JSON 的 `error` 字段中。

---

## 附录：端点速查表

### GET 端点速查

| 端点 | 参数 | 用途 |
|------|------|------|
| `/` | — | 编辑器主页 |
| `/api/status` | — | 上下文用量 |
| `/api/cache-stats` | — | 缓存统计 |
| `/api/version` | — | 版本号 |
| `/api/list-sessions` | — | 所有会话列表 |
| `/api/system-health` | — | 系统健康 |
| `/api/switch-session` | `key` | 切换会话 |
| `/api/delete-session` | `key`/`sessionKey` | 删除会话 |
| `/api/session` | `key` | 会话数据 |
| `/api/session-rpc` | — | RPC 会话消息 |
| `/api/digestion-status` | — | 消化状态 |
| `/api/digestion-skill` | — | 监控栏状态 |
| `/api/digestion-history` | — | 消化历史 |
| `/api/backlog` | — | 待办清单 |
| `/api/backup-stale` | — | 备份过时 |
| `/api/thinking-status` | — | 思考状态 |
| `/api/weaponry-toggle` | — | 武器库状态 |
| `/api/plugin-health` | — | 插件健康 |
| `/api/last-injection` | — | 最近注入 |
| `/api/last-processing` | — | 最近处理 |
| `/api/subagent-history` | — | 子代理历史 |
| `/api/tb-files` | `folder` | 文件列表 |
| `/api/tb-read-file` | `path`, `pw` | 读文件 |
| `/api/list-files` | `folder`/`path` | 列 .md 文件 |
| `/api/browse-dirs` | — | 根目录浏览 |
| `/api/quickcheck` | — | 健康检查 |
| `/api/secretary-log` | — | 秘书日志 |
| `/api/facts-stale` | — | 事实过时 |
| `/api/reminders` | — | 提醒列表 |
| `/api/backups` | — | 备份列表 |
| `/api/subagents` | — | 子代理列表 |
| `/api/memory-files` | — | 记忆文件列表 |
| `/api/memory-file` | `name` | 读记忆文件 |
| `/api/awake-questions/list` | — | 唤醒题库 |
| `/api/encrypt...` | `folder` | 加密状态 |
| `/paper-annotated.html` | — | 论文标注 |
| `/static/*` | — | 静态资源 |

### POST 端点速查

| 端点 | 必需字段 | 用途 |
|------|----------|------|
| `/api/ping` | — | 连通性测试 |
| `/api/abort` | — | 停止 AI |
| `/api/restart-http` | — | 重启服务 |
| `/api/pet-me` | — | 静默处理 |
| `/api/trim-session` | — | 裁剪会话 |
| `/api/thinking-toggle` | — | 思考循环 |
| `/api/weaponry-toggle` | `enable` | 武器库开关 |
| `/api/inject` | `message` | 注入消息 |
| `/api/edit` | `index`, `text`, `approved` | 截断编辑 |
| `/api/clear-inject-lock` | — | 清除锁 |
| `/api/pulse` | `mode` | 保活脉冲 |
| `/api/momo` | `sub_action` | 摸摸协议 |
| `/api/spawn-subagent` | `task`, `model` | Spawn |
| `/api/auth-subagent` | — | 授权 |
| `/api/exec-subagent` | `task`, `model` | Exec |
| `/api/reminders` | `action` | 提醒管理 |
| `/api/memory-file` | `name`, `content` | 保存记忆 |
| `/api/awake-questions/list` | — | 题库列表 |
| `/api/awake-questions/save` | `content` | 保存题库 |
| `/api/tts` | `text` | 语音合成 |
| `/api/encrypt` | `password`, `folder` | 加密文件夹 |
| `/api/tb-save-file` | `path`, `content` | 保存文件 |
| `/api/tb-create-file` | `folder`, `name` | 创建文件 |
| `/api/tb-rename-file` | `old_path`, `new_name` | 重命名 |
| `/api/tb-delete-file` | `path` | 删除文件 |
