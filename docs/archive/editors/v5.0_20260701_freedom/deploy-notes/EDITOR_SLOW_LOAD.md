# 编辑器首次加载缓慢诊断报告

> 诊断时间: 2026-06-26 00:50 CST
> 诊断人: 子代理（深度 1）
> 运行版本: edit-web.py (1935 行，试错版含 `subprocess.run(timeout=10)`)

---

## 1. 当前状态：所有 API 正常，无明显延迟

逐一测试了编辑器所有开机加载的 API 端点，**全部在 0.02–0.25 秒内响应**：

| API | 实测延迟 | 说明 |
|-----|---------|------|
| `/api/status` | 0.06s | 读取 sessions.json + 模型配置 |
| `/api/session` | 0.23s | 读会话文件 + JSON 解析 |
| `/api/session?fresh=1` | 0.21s | 同上 |
| `/api/list-sessions` | 0.08s | 扫描 sessions.json + 各 .jsonl |
| `/api/cache-stats` | 0.03s | cache_monitor 模块 |
| `/api/memory-files` | 0.03s | 扫描 memory/ 目录 |
| `/api/backlog` | 0.02s | 读 backlog.md |
| `/api/backup-stale` | 0.02s | 文件 mtime 对比 |
| `/api/digestion-skill` | 0.03s | 读多个文件 + 断言计数 |
| `/api/thinking-status` | 0.05s | 读状态文件 |
| `/api/weaponry-toggle` | 0.02s | 读 cron jobs.json |
| `/api/system-health` | 0.03s | 读 cron + 上下文文件 |
| `/api/secretary-log` | 0.02s | 读秘书观察.log |
| `/api/reminders` | 0.02s | 读 reminders.json |
| `/api/browse-dirs` | 0.02s | os.listdir |
| Gateway `/status` | 0.72s | curl 到 32823，略慢但无大碍 |

**关键结论：当前运行的编辑器实例性能正常。** 接近 1 分钟的首次加载要么是历史问题（已通过之前的改动修复），要么是瞬态条件（文件系统冷缓存 + 并发写入竞争）。

---

## 2. 子方向排查结果

### ✅ 方向 A：Inject Lock 阻塞 → 非根因

- `.locks/` 目录完全为空，无残留锁文件
- Inject 锁只阻塞 `inject_via_websocket()` 一个函数（TTL=20 秒），**不影响其他 API handler**
- `_cleanup_lock()` 在 inject 的所有出口路径都被调用（正常返回、超时、异常）
- 前端开机调用链中**无任何 inject API 调用**

### ✅ 方向 B：subprocess.run 分布 → 安全

```
行 240: inject_via_websocket()   timeout=10  → 只在手动 inject/pulse 时触发
行 515: fetch_session_via_gateway() timeout=5 → 不用于默认开机页（仅 session-rpc 可选路径）
行 1493: 注入(脉冲)             timeout=60   → 只在 pulse 时触发
行 1635: spawn_subagent()       timeout 可变   → 只在显式子代理时触发
```

**前端开机页不会触发任何 subprocess.run 调用**。所有开机 API 全是文件读取 + JSON 解析。

### ✅ 方向 C：文件系统 IO 慢 → 非根因

- `memory/` 目录：43 个文件，约 597KB，ls/cat 均在 <0.01s
- 会话目录：34 个用户会话 .jsonl 文件，总大小 34MB，全量扫描 <0.13s
- 文件系统是 btrfs（同卷，无跨文件系统软链）
- 最大会话文件 2.4MB（约 1000 行），cold read 约 0.03–0.06s

### ✅ 方向 D：自动存档线程 → 非根因

- 开机时 `_momo_auto_save_loop()` 调用 `start_momo_auto_save()`，在新线程中执行
- `momo_pack()` 复制 51 个文件，仅需 ~0.07–0.19s
- 由于在后台线程执行，**不阻塞 HTTP server 启动**

### ✅ 方向 E：Gateway 通信延迟 → 非根因

- Gateway `/status` 响应 0.72s（略有延迟但远不到分钟级）
- 开机 API 均不依赖 Gateway

### ✅ 方向 F：逐个 API 测试 → 全部正常

已在第一部分列出。

---

## 3. 根因分析

### 真实根因（推测）

当前代码层面**不存在导致分钟级首次加载的缺陷**。最可能的原因是 **历史问题**：

#### 根因 1：守护脚本互相杀进程（已修复）
> 之前刚解决了守护脚本互相杀进程的问题。

如果一个脚本杀掉了编辑器的进程，新的编辑器进程启动时可能需要重新读写文件系统（冷缓存），加上守护脚本反复重启，造成用户感知为"首次加载很慢"。

#### 根因 2：`subprocess.run` 无 timeout（已修复）
试错版加的 `timeout=10` 之前在 inject 上可能缺失或 timeout 更大，导致失败时释放不彻底。

#### 根因 3：（低概率）浏览器端并发请求累积
前端开机时约 5 个 API 请求同时发出（listSessions、sessionFresh、status、cacheStats、各组件 init）。如果网速慢或浏览器单域名连接数限制（HTTP/1.1 通常 6 个并行），在极端网络条件下可能影响感知。

### 汇总

| 假设 | 概率 | 依据 |
|------|------|------|
| 守护脚本互杀的历史遗留 | 高 | 已知已修复，修复前会导致重启周期 |
| inject timeout 缺失 | 中 | 试错版才加上的 timeout=10 |
| 文件系统冷缓存 | 中低 | btrfs + 34MB 数据，cold read 也应 <2s |
| 锁残留阻塞 | 低 | `.locks/` 空，且锁只影响 inject handler |
| subprocess 慢 | 无 | 开机 API 不触发 subprocess |

---

## 4. 修复方案

### 已存在的防护措施（已验证正常）

1. ✅ `INJECT_LOCK_TTL=20` — 锁自动过期
2. ✅ `subprocess.run(timeout=10)` — inject 超时兜底
3. ✅ `_cleanup_lock()` 在所有出口调用
4. ✅ 后台线程执行 momo_pack，不阻塞 HTTP server

### 建议追加的加固（可选）

1. **给 `list_all_sessions()` 加 LRU 缓存**，减少开机时的文件扫描（虽然不是瓶颈，但可以做得更好）
2. **给 `read_session()` 加文件修改时间缓存**，避免每秒轮询重复读大文件
3. **检查是否所有 handler 有全局异常兜底**（已有 `try/except` 外层包裹）

### 不需要改的（已验证安全）

- Inject 锁机制：设计合理，只影响 inject，不影响其他 API
- Momo 自动存档：后台线程，不阻塞
- 各 handler 的 subprocess.run：均加了 timeout，且开机不触发

---

## 5. 修复后验证方法

如果后续再出现类似问题，按以下顺序诊断：

```bash
# 1. 检查锁文件残留
ls -la /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/.locks/

# 2. 测试各 API 延迟（跑完看哪一行时间异常）
echo "=== status ==="   && time curl -s http://127.0.0.1:18888/api/status -o /dev/null
echo "=== session ==="  && time curl -s http://127.0.0.1:18888/api/session -o /dev/null
echo "=== list-sessions ===" && time curl -s http://127.0.0.1:18888/api/list-sessions -o /dev/null
echo "=== cache-stats ===" && time curl -s http://127.0.0.1:18888/api/cache-stats -o /dev/null
echo "=== memory-files ===" && time curl -s http://127.0.0.1:18888/api/memory-files -o /dev/null
echo "=== backlog ===" && time curl -s http://127.0.0.1:18888/api/backlog -o /dev/null
echo "=== digestion-skill ===" && time curl -s http://127.0.0.1:18888/api/digestion-skill -o /dev/null

# 3. 如果 session API 慢，检查会话文件大小
wc -c /vol1/@apphome/trim.openclaw/data/home/.openclaw/agents/main/sessions/*.jsonl | sort -n | tail -5

# 4. 检查是否有 stuck 的 subprocess
ps aux | grep -E "bun|python3.*edit" | grep -v grep

# 5. 快速健康检查
curl -s http://127.0.0.1:18888/api/quickcheck | python3 -m json.tool
```

### 正常参考值

- 各 API 延迟：**< 0.3s**
- 全量 API 冷启动（累计）：**< 2s**
- Gateway 响应：**< 1s**

---

## 6. 诊断过程数据

| 指标 | 值 |
|------|-----|
| 编辑器 PID | 514381 |
| 运行时间 | ~8 分钟（开机于 00:42） |
| 会话目录总大小 | 34MB |
| 用户会话数 | 34 |
| trajectory 文件数 | 37 |
| memory 文件数 | 43 |
| momo_pack 启动时间 | ~0.07s（51 个文件） |
| SQLite/lock 残留 | 无 |
| 挂载文件系统 | btrfs (同卷) |
| 可用内存 | 1402MB |
| 编辑器进程内存 | ~44MB RSS |
