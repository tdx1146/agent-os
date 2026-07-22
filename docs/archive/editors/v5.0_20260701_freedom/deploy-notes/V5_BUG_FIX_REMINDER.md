# V5 提醒系统修复报告

**日期:** 2026-07-01
**修复版本:** v5.0 "自由王国"

---

## 根因

前后端 API 协议不匹配，导致提醒系统的 ✓ 复选框点击无效。

### 前端发送格式（修改前）
```javascript
// scripts/static/js/core.js (lines 52-53)
remindersDone: (i) => api.post('/api/reminders', {done: i}),
remindersClearClearDone: () => api.post('/api/reminders', {clear_done: true}),
```
→ 发送 `{done: 3}` 或 `{clear_done: true}`

### 后端期望格式
```python
# scripts/handlers/helper_handler.py (line 166)
action = data.get('action', 'add')
```
→ 期待 `{action: 'done', id: 3}` 或 `{action: 'clear_done'}`

因为没有 `action` 字段，后端默认走 `add` 分支 → 添加一条空白提醒，而不标记完成。

## 修复内容

### 修改文件
`scripts/static/js/core.js` 第 52–53 行

### 修改内容
```diff
-  remindersDone: (i) => api.post('/api/reminders', {done: i}),
-  remindersClearDone: () => api.post('/api/reminders', {clear_done: true}),
+  remindersDone: (i) => api.post('/api/reminders', {action: 'done', id: i}),
+  remindersClearDone: () => api.post('/api/reminders', {action: 'clear_done'}),
```

### 改动说明
- `remindersDone`: 改用 `{action: 'done', id: i}` 匹配后端期待
- `remindersClearDone`: 改用 `{action: 'clear_done'}` 匹配后端期待
- 后端 `remindersAdd` 不受影响（已有 `{text, assignee}`，后端 `action='add'` 走默认分支）

## 验证结果

| 项目 | 状态 |
|------|------|
| JS 语法验证 (acorn) | ✅ 通过 |
| 修改后字段匹配 | ✅ `{action: 'done', id: n}` / `{action: 'clear_done'}` |
| 后端无修改 | ✅ 仅改前端 |
| 重启运行 | ✅ 完成 |
