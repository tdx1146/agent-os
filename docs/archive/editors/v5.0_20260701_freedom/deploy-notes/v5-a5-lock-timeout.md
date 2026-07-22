# v5-a5: inject 锁超时修复

## 改动描述

修复 inject 互斥锁没有超时兜底的问题。当一个 inject 子进程卡住时，锁文件会永久残留导致后续所有 inject 被拒绝。

### 改动的文件

- `scripts/edit-web.py` — `_cleanup_lock()` 函数

### 具体变更

`_cleanup_lock()` 在删除锁文件前增加年龄检查：

```python
def _cleanup_lock():
    """清理注入锁文件（含 TTL 超时兜底）"""
    try:
        if os.path.exists(INJECT_LOCK_FILE):
            mtime = os.path.getmtime(INJECT_LOCK_FILE)
            age = time.time() - mtime
            if age > INJECT_LOCK_TTL:
                os.remove(INJECT_LOCK_FILE)
                print(f"[轻如烟] [锁超时] 锁文件超过 {INJECT_LOCK_TTL}s（实际 {age:.0f}s），强制清除", file=sys.stderr)
                return
            os.remove(INJECT_LOCK_FILE)
    except OSError:
        pass
```

### 运行原理

- `INJECT_LOCK_TTL` 环境变量控制超时阈值，默认 **20 秒**（与 inject_via_websocket 中的锁拒绝检查一致）
- 锁文件 mtime 超过 TTL → 强制删除并打印警告到 stderr
- 锁文件未超时 → 正常删除（等待中的子进程释放后清理）
- 锁文件不存在 → 无操作

### 验证结果

| 检查项 | 状态 |
|---|---|
| 备份 (.bak.v5-a5) | ✅ |
| import 加载 | ✅ 无错误 |
| API 返回 | ✅ HTTP 200 |

### 部署

```bash
# 重启后自动生效
kill -9 $(lsof -ti :18888) 2>/dev/null
cd /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts && nohup python3 edit-web.py &
```
