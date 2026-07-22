# 🔍 编辑器频繁崩溃诊断报告

> 报告生成时间：2026-06-26 00:30 (GMT+8)
> 故障现象：dandan 在外网通过 IPv6 访问 `qh.tdx1146.com:18888`，重启编辑器后过几分钟就打不开

---

## 1. 崩溃根因

### 主要根因：`subprocess.run(timeout=10)` 阻塞请求线程 + Gateway 连接不稳定 导致进程被守护脚本杀死

**这不是一个直接的「代码 bug 导致 Python 异常退出」，而是一个「级联失效」问题：**

1. **Inject-helper 的 WebSocket 帧超时（2秒）在 Gateway 过载时会频繁触发**
   - inject-helper.mjs 第 182 行 `recvFrame(timeoutMs = 2000)`——每帧等待仅 2 秒
   - 注入日志证实存在超时：
     ```
     Error: timeout
     {"ok":false,"error":"timeout"}
     ```
   - Gateway 是本地 `127.0.0.1` 连接，正常情况下 ~45ms 往返，但当 Gateway 繁忙时，WebSocket 握手/响应延迟会超过 2 秒

2. **`subprocess.run(timeout=10)` 将 inject-helper 的超时放大到 10 秒阻塞**
   - 新的 `subprocess.run` 等待 bun 进程退出。如果 inject-helper 因 WebSocket 帧超时而挂起（最长 2s/帧 × 多帧），subprocess.run 会阻塞当前线程最多 10 秒

3. **多线程累积 → 资源耗尽 → 进程被系统/OOM 杀死**
   - `ThreadingHTTPServer` 不会限制线程数，每个请求创建新线程
   - 当多个 inject 请求并发进入（浏览器自动重试/轮询），每个线程都持有：
     - 一个文件描述符（`logf`）
     - 一个 bun 子进程
     - 一个 TCP 连接到 Gateway
   - 虽然单个线程 300ms 看似短暂，但在 Gateway 不稳定时，线程可能堆积到数百个
   - 进程最终被 OOM Killer 或 `ulimit` 限制杀死

4. **Watchdog 脚本加剧了崩溃循环**
   - 存在多个守护脚本：
     - `watchdog.sh`（每 30 秒检查）
     - `health-loop.sh`（每 5 分钟检查）
     - `health-check.sh`
   - 当进程因资源耗尽而响应缓慢（curl --connect-timeout 5 超时），watchdog 会重启进程
   - 重启后的新进程很快重复上述循环

### 次要因素：资源泄漏

- `logf` 文件对象在 `inject_via_websocket` 中没有显式 `close()`
- 每个 inject 请求打开一个日志文件并传给 `subprocess.run`，引用释放后依赖 GC 关闭
- 正常情况下 364 个文件描述符远低于 `ulimit -n = 524288`，但非主要问题

---

## 2. 代码改动详情

### 改动对比（备份 `edit-web.py.bak.20260626_0007` → 当前 `edit-web.py`）

#### 改动位置：`inject_via_websocket()` 函数（第 231-255 行）

| 旧代码 (Popen) | 新代码 (subprocess.run) |
|---|---|
| `subprocess.Popen(...)` → 立刻返回 | `subprocess.run(..., timeout=10)` → 同步等待 |
| `return {"ok": True}`（假的成功） | 返回真实结果（ok/error/timeout） |
| 可能抛异常继续往上抛 | 所有异常被捕获并返回 error 响应 |
| 锁清理？不做 | 所有路径都调用 `_cleanup_lock()` |

**目标正确：** 前端需要真实结果而非假的 "ok"
**实现有代价：** 阻塞线程

### 具体代码关键行

```python
# 第 231 行：定义 timeout 但从未使用！
timeout = int(os.environ.get('INJECT_TIMEOUT', 60))
# 第 243 行：硬编码 timeout=10，忽略上述环境变量
r = subprocess.run(
    [path('BUN_BIN'), helper, session_key, message],
    stdout=logf, stderr=subprocess.STDOUT,
    env=env, timeout=10, capture_output=False  # ← 硬编码
)
```

---

## 3. 其他排查项的结论

| 排查项 | 结果 |
|---|---|
| **HTTP server 模型** | ✅ `ThreadingHTTPServer`（多线程），不是单线程阻塞 |
| **自动存档** | ✅ 运行在独立 daemon 线程中，不阻塞主线程 |
| **锁竞争** | ✅ INJECT_LOCK_FILE 在所有路径正确清理 |
| **inject-helper.mjs** | ✅ 无改动，备份文件不存在 |
| **系统资源限制** | `ulimit -n=524288` 充裕，但不排除并发线程数内存压力 |
| **当前进程状态** | ❌ 未找到运行中的 edit-web 进程（已崩溃/被杀死） |

---

## 4. 修正/修复方案

### 方案 A：Fire-and-Forget + 异步结果轮询（推荐）

回归 Popen 模式，但用文件/信号传递真实结果，不让前端等待：

```python
# inject_via_websocket 保持非阻塞
subprocess.Popen([path('BUN_BIN'), helper, session_key, message],
                  stdout=logf, stderr=subprocess.STDOUT, env=env)
_cleanup_lock()
return {"ok": True, "note": "inject started"}
```

前端保持原有的轮询机制（检查消息是否出现）。这样：
- 不阻塞任何线程
- 不创建堆积的线程和子进程
- 对 Gateway 不稳定天然容忍

### 方案 B：线程池隔离（保留同步结果）

如果前端需要真实结果，用 `concurrent.futures.ThreadPoolExecutor` 隔离长时间阻塞操作：

```python
from concurrent.futures import ThreadPoolExecutor

_INJECT_EXECUTOR = ThreadPoolExecutor(max_workers=4)

def inject_via_websocket(session_key, message, bypass_lock=False):
    # ... 锁检查（不变） ...
    
    # 提交到线程池，不阻塞当前 ThreadingHTTPServer 线程
    future = _INJECT_EXECUTOR.submit(_inject_blocking, helper, session_key, message, env)
    try:
        result = future.result(timeout=12)  # 线程池内部等待
        return result
    except TimeoutError:
        return {"ok": False, "error": "inject internal timeout"}
```

最大 4 个并行 inject 线程，不会无限堆积。

### 方案 C：保留 Popen + 独立状态检查（最安全）

旧 Popen + 在新线程中等待结果写入状态文件，前端通过 `/api/inject-status` 轮询。

---

## 5. 立即缓解措施

1. **杀掉残留的 watchdog 脚本**（防止陷入重启循环）
   ```bash
   pkill -f health-loop.sh 2>/dev/null
   pkill -f watchdog.sh 2>/dev/null
   ```

2. **临时恢复为 Popen**（如果授权回滚）
   ```bash
   cp edit-web.py.bak.20260626_0007 edit-web.py
   ```

3. **启动编辑器并监控 stderr**
   ```bash
   cd /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts
   python3 edit-web.py 2>/tmp/editor_stderr.$(date +%s).log &
   ```

---

## 6. 附录

### 注入日志样本（正常）

```
[timing] recv challenge: 22ms
[timing] connect sent: 24ms
[timing] recv connect ack: 48ms
{"ok":true}
```

### 注入日志样本（超时）

```
[timing] recv challenge: 25ms
[timing] connect sent: 27ms
[timing] recv connect ack: 44ms
Error: timeout
{"ok":false,"error":"timeout"}
```

> 注：`Error: timeout` 来自 inject-helper.mjs 的 `recvFrame(2000)` 2 秒帧超时

### 关联的守护脚本

| 脚本 | 检查间隔 | 超时 | 动作 |
|---|---|---|---|
| `watchdog.sh` | 30 秒 | 5 秒 | 重启编辑进程 |
| `health-loop.sh` | 5 分钟 | 默认 | 重启编辑进程 |
| `health-check.sh` | N/A | 默认 | 状态检查 |

### 环境

- Python 3.11.2
- `ulimit -n`: 524288
- 服务器: `ThreadingHTTPServer` on IPv6 `::` port 18888
- Gateway: 本地 `127.0.0.1` (端口来自配置)
