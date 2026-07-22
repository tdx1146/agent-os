# 轻如烟编辑器 (openclaw-control-ui) 版本记录

> 本机 OpenClaw v2026.5.4 编辑器补丁记录

---

## v2026.7.17-patch1 — Bug修复

### Bug A: 切换会话后原 session 消失

**现象：** 从 session A 切换到 session B，在 B 中发送消息后，A 从会话列表消失（间歇性复现）。

**根因：** `sessions.changed` 事件处理中 `Su(e)` 裸调用，未传 `{activeMinutes:0, limit:0, includeGlobal, includeUnknown, showArchived}` overrides，导致使用默认 120 分钟活跃过滤 + agent ID 过滤 → 原 session 被排除。

**修复：** `index-BS51oJri.js` — `AL()` 函数中 `Su(e)` → `Su(e,{activeMinutes:0,limit:0,includeGlobal:!0,includeUnknown:!0,showArchived:e.sessionsShowArchived})`

### Bug B: 截断发送全部清空

**现象：** 无论选择保留几轮，截断并发送后所有历史消息被清空。

**根因：** `gf(e)` 调用 `sessions.reset({key})`，该 API 不接受轮数参数，永远全量重置。

**修复：**
- 后端新增 `sessions.compact` 的 `keepRounds` 参数（按对话轮数截断）
- 轮数定义：1 user 消息 + 后续所有 assistant/tool/toolresult 消息 = 1 轮
- 新工具函数 `parseTranscriptByRounds()` 在 `session-utils.fs-D-MAAH1K.js`
- 前端 `gf(e)` 和 `onClearHistory` 改为调用 `sessions.compact({key, keepRounds: 2})`

**修改文件：**
- `dist/protocol-BhTUkTma.js` — schema 定义
- `dist/server-methods-DTGNFOnM.js` — handler 新增 keepRounds 分支
- `dist/session-utils.fs-D-MAAH1K.js` — 新增 parseTranscriptByRounds
- `dist/control-ui/assets/index-BS51oJri.js` — 前端调用链路
