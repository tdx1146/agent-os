# 轻如烟 对话编辑器 — 系统说明书

> 最后更新：2026-06-13 02:07
> 对应 commit：截断代码重写 + 会话列表修复 + 全部显示模式

## 一、架构全景

```
scripts/
├── edit-web.py              ← 主后端（HTTP 服务器，端口 18888）
├── inject-helper.mjs         ← WS 注入通道（Node.js 子进程）
├── cache_stats_helper.py     ← 上下文缓存统计
├── editor-config.json        ← 配置（端口、Gateway 地址等）
│
├── utils/                    ← 后端工具包
│   ├── crypto.py             ← Ed25519 加密（尚在被调用）
│   ├── inject.py             ← 消息注入 WS 封装
│   ├── momo.py               ← 摸摸协议（打包/存档/搜索）
│   ├── secretary.py          ← 小秘书（文件变更追踪）
│   ├── session.py            ← 会话文件读写（JSONL）
│   └── tb_handler.py         ← 文件浏览器后端
│
├── handlers/                 ← 请求路由（前后端分离产物）
│   ├── router.py             ← 统一路由分发
│   ├── session_handler.py    ← 会话切换/列表 API
│   ├── momo_handler.py       ← 摸摸 API
│   ├── file_handler.py       ← 文件浏览 API
│   ├── inject_handler.py     ← 注入 API
│   ├── crypto_handler.py     ← 加密 API
│   ├── system_handler.py     ← 系统状态 API
│   └── helper_handler.py     ← 辅助 API
│
└── static/                   ← 纯前端
    ├── index.html            ← 入口
    ├── favicon.ico
    ├── css/styles.css
    └── js/
        ├── core.js           ← 状态层（store）+ API 层 + 轮询
        ├── app.js            ← 组件框架（CL.register）
        ├── components.js     ← UI 组件（会话选择器/消化栏/系统健康等）
        ├── render.js         ← 渲染层（消息/分页/全部显示）
        ├── editor.js         ← 编辑/截断面板逻辑
        ├── awake.js          ← 消息发送/题库/唤醒
        ├── momo.js           ← 摸摸协议前端
        ├── dashboard.js      ← 仪表盘
        ├── file-browser.js   ← 文件浏览器前端
        └── subagent.js       ← 子代理管理
```

## 二、部署方式

```bash
cd scripts/
python3 edit-web.py
```

自动监听 `0.0.0.0:18888`（HTTP）和 `0.0.0.0:18889`（HTTPS 自签名）。

自动发现 Gateway 端口（从 `openclaw.json` 读取），自动连接 WebSocket 用于消息注入。

## 三、核心流程

### 消息发送（注入）
1. 用户点「发送」→ POST `/api/inject`
2. 后端调用 `inject_via_websocket()` → 通过 inject-helper.mjs 向 Gateway WS 发消息
3. 前端 3 秒轮询 `/api/session?fresh=1` 等待回复出现

### 截断（已重写，2026-06-13）
1. 点「编辑」→ 弹出编辑面板
2. 修改用户消息 → 「保存截断」
3. 后端 `edit_message()`：
   - 读 JSONL 文件 → 定位用户消息位置
   - 安全检查（距离末尾不超过 `MAX_EDIT_DEPTH` 轮，默认 1 轮）
   - 备份到 `edit-web-backups/pre-edit.{时间戳}.jsonl`
   - 截断（保留到目标行前）
   - 返回截断条数
4. 前端立即注入修改后的消息 → Gateway 重新生成回复

**安全铁律（代码级硬化）：**
- `MAX_EDIT_DEPTH = 1`：只能截断最近 1 轮
- `approved=True` 绕过安全检查（主人授权）
- 编辑前端有勾选确认框，勾选后传 `approved=true`

### 会话切换
1. 左上角下拉显示所有用户可见会话（含 `:dashboard:`）
2. `set_active_session_key()` 设置目标 key
3. 后续所有 API 读取该 key 对应的 JSONL 文件
4. 支持 `orphan:` 前缀（直接从文件名反查文件路径）

## 四、数据格式

### sessions.json（Gateway 维护）
```json
{
  "agent:main:main": {
    "sessionFile": "/path/to/uuid.jsonl",
    "updatedAt": 1781285779000,
    "totalTokens": 150000
  }
}
```

### JSONL 轮次文件（每行一条 JSON）
```json
{"id":"msg1","type":"message","message":{"role":"user","content":"用户消息"},"timestamp":1700000000000}
{"id":"msg2","type":"message","message":{"role":"assistant","content":[{"type":"text","text":"AI回复"}]},"timestamp":1700000001000}
```

## 五、踩坑记录

### 1. 截断代码安全性（2026-06-13）
**问题**：旧版有 3 层安全检查（距离末尾检查 + 10% 头部保护 + 50% 阈值保护），逻辑复杂且出 bug。
**修复**：删了所有旧逻辑，重写为 30 行简洁版。只有 `MAX_EDIT_DEPTH` + `approved` 两层。

### 2. session 列表不显示（2026-06-13）
**问题**：`list_all_sessions()` 过滤了 `:dashboard:` 会话，导致 dashboard 会话不出现在下拉列表中。
**修复**：移除了对 `:dashboard:` 的过滤。

### 3. 会话选择器下拉为空（2026-06-13）
**问题**：`components.js` `sessionSelector` 的 `init` 里 `ctx._list = []` 后没调 API 加载列表。
**修复**：在 `init` 和 20 秒轮询里都加了 `api.listSessions()`。

### 4. 空 assistant 消息显示（2026-06-13）
**问题**：tool call 占位被渲染成 "(AI回复为空)"，页面被几十条空消息刷屏。
**修复**：`renderMessagesHtml()` 过滤掉无文本无思考内容的 assistant 消息。

### 5. 小秘书插件断连（2026-06-12）
**问题**：秘书模块依赖 inject-helper.mjs 的 WS 连接，Gateway 重启后通道断开无法自动重连。
**修复**：inject-helper.mjs 加入自动重连机制，每分钟检测一次连接状态。

### 6. Gateway WS 认证（2026-05-18）
**问题**：Gateway 换端口/重启后，WS 签名失效，注入失败。
**修复**：`crypto.py` 用 Ed25519 签名，认证流程：读取 device.json → challenge → sign → 连接。

### 7. memory/ 软链接逃逸（2026-06-03）
**问题**：`workspace/memory` 是软链接指向 `/vol2/.../memory`，read/write 工具无法跨沙盒访问。
**修复**：反转软链接方向 —— `workspace/memory` 变成真实目录，`/vol2` 路径指向它。

### 8. 注入锁单向阀（2026-05-18）
**问题**：AI 自我递归注入导致 token 耗尽和会话污染。
**修复**：每用户轮最多 1 次注入，由用户下一条消息触发清除。代码实现在 `utils/inject.py`。

### 9. 过度安全检查导致截断失败（2026-06-13）
**问题**：旧版有 `target_line < total_raw * 0.1` 保护，但 userIndex 在会话文件被压缩后容易偏移，误触发头部保护拒绝截断。
**修复**：移除比率检查，只保留距离末尾轮数检查。同时 `_get_session_data()` 传 `userIndex` 的顺序已修复（从旧到新→从新到旧统一）。**

## 六、环境依赖

- **Python**：3.11（http.server 内置，无第三方依赖）
- **Node.js**：v22+（inject-helper.mjs 用 ESM）
- **OpenClaw**：v2026.3.13+
- **Gateway 端口**：自动发现（写死在 17587，旧版 22881，从 openclaw.json 读取）

## 七、启动后验证

1. 浏览器打开 `http://nas-ip:18888`
2. 查看左上角：显示「当前会话」代表连接成功
3. 点「全部显示」确认历史消息完整
4. 下拉选择「仪表盘」确认会话切换正常
5. 测试截断：点编辑图标 → 改文字 → 保存 → 确认 AI 重新回复

## 八、相关文件

- `/vol1/@apphome/trim.openclaw/data/home/.openclaw/agents/main/sessions/` — 会话数据目录
- `/vol1/@apphome/trim.openclaw/data/home/.openclaw/agents/main/sessions/sessions.json` — 会话注册表
- `../.locks/.inject_lock` — 注入锁文件
- `../memory/` — 轮感/记忆文件
- `../scripts/edit-web-backups/` — 编辑截断自动备份
