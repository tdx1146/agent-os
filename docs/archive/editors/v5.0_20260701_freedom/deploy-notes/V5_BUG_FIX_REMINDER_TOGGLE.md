# V5 Bug Fix: 提醒清单「已勾选→直接消失」逻辑修复

## 问题

打勾后条目立刻消失，「清理已完成」按钮被架空。

## 根因

1. **后端过滤**：`secretary_remind()` 返回时过滤了 `done=True` 的条目，导致刚打勾就不可见
2. **只设 True**：`done` action 只设 `True`，无法切换回未完成
3. **前端无区分**：渲染时不读 `r.done` 字段，无论状态都显示空心 ✓

## 修改

### 1. `utils/secretary.py` — 不过滤 done

| 修改前 | 修改后 |
|--------|--------|
| 返回 `[r for r in reminders if not r.get('done')]` | 返回全部 `load_reminders(light_smoke_dir)` |

### 2. `handlers/helper_handler.py` — done action 改为 toggle

修改前：
```python
r['done'] = True
handler._send_json(200, {"ok": True})
```

修改后：
```python
r['done'] = not r.get('done', False)  # toggle
found = r
...
handler._send_json(200, {"ok": True, "done": found['done'] if found else False})
```

### 3. `static/js/render.js` — 前端根据 `r.done` 区分渲染

- done=True → ✅ 按钮 + 灰色删除线文字
- done=False → ✓ 按钮 + 正常颜色文字

## 验证

- ✅ acorn JS 语法检查通过
- ✅ `python3 -m py_compile` 两文件通过
- ✅ `curl` 打勾 → 返回包含 done=true 的条目
- ✅ 再次打勾 → toggle 回 done=false
- ✅ `clear_done` 只删除 done=true 的条目

## 备份

原始文件已备份至 `.v5_bak/`：
- `.v5_bak/secretary.py.bak`
- `.v5_bak/helper_handler.py.bak`
- `.v5_bak/render.js.bak`

## 完成时间

2026-07-01 22:57 (CST)
