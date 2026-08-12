#!/bin/bash
# Agent OS 一键启动
# 启动所有守护进程
# 2026-08-10 部署统一化：VERIFY_HOME 从 env.local 读取，缺失时相对推导

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_OS_HOME="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -f "$AGENT_OS_HOME/env.local" ]; then
    set -a; . "$AGENT_OS_HOME/env.local"; set +a
fi
# 玄鉴已并入 agent-os/xuanjian（2026-08-12）；优先新路径，旧同构沙盘回退（本机运行实例仍在其 data/）。
if [ -d "$AGENT_OS_HOME/xuanjian/src" ]; then
    VERIFY_HOME="${VERIFY_HOME:-$AGENT_OS_HOME/xuanjian}"
else
    VERIFY_HOME="${VERIFY_HOME:-$AGENT_OS_HOME/../AgentOS-IsoSand/同构沙盘}"
fi

echo "=== Agent OS 启动 ==="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "目录: $SCRIPT_DIR"
echo ""

# 1. 启动调度器
echo "--- 事件总线调度器 ---"
bash "$SCRIPT_DIR/start_scheduler.sh"
echo ""

# 2. 启动消费者
echo "--- 事件总线消费者 ---"
bash "$SCRIPT_DIR/start_consumer.sh"
echo ""

# 3. 验证
echo "=== 进程状态 ==="
sleep 1
ps aux | grep -E "\.run_(scheduler|consumer)" | grep -v grep || echo "（调度器/消费者进程未见，请查日志）"
echo ""

# 4. 检查玄鉴
echo "--- 玄鉴守护进程 ---"
if [ -f "$VERIFY_HOME/data/daemon.pid" ]; then
    VERIFY_PID=$(cat "$VERIFY_HOME/data/daemon.pid")
    if kill -0 "$VERIFY_PID" 2>/dev/null; then
        echo "[verify_daemon] ✅ 运行中 (PID: $VERIFY_PID)"
    else
        echo "[verify_daemon] ❌ PID文件存在但进程未运行"
    fi
else
    echo "[verify_daemon] ⚠️ PID文件不存在"
fi

echo ""
echo "=== 数据文件 ==="
ls -la "$SCRIPT_DIR/data/"
echo ""
echo "=== ✅ Agent OS 启动完成 ==="
