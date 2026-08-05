#!/bin/bash
# Agent OS 停止

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Agent OS 停止 ==="

# 停止调度器
if [ -f "$SCRIPT_DIR/data/scheduler.pid" ]; then
    PID=$(cat "$SCRIPT_DIR/data/scheduler.pid")
    kill "$PID" 2>/dev/null && echo "[scheduler] ⏹️ 已停止 (PID: $PID)" || echo "[scheduler] ⚠️ 进程不存在"
    rm -f "$SCRIPT_DIR/data/scheduler.pid"
else
    echo "[scheduler] PID文件不存在"
fi

# 停止消费者
if [ -f "$SCRIPT_DIR/data/consumer.pid" ]; then
    PID=$(cat "$SCRIPT_DIR/data/consumer.pid")
    kill "$PID" 2>/dev/null && echo "[consumer] ⏹️ 已停止 (PID: $PID)" || echo "[consumer] ⚠️ 进程不存在"
    rm -f "$SCRIPT_DIR/data/consumer.pid"
else
    echo "[consumer] PID文件不存在"
fi

echo ""
echo "=== 剩余进程 ==="
ps aux | grep -E "(task_scheduler|event_consumer)" | grep -v grep || echo "无"
echo ""
echo "=== ✅ Agent OS 已停止 ==="
