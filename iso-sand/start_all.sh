#!/bin/bash
# Agent OS 一键启动
# 启动所有守护进程

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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
ps aux | grep -E "(task_scheduler|event_consumer)" | grep -v grep
echo ""

# 4. 检查玄鉴
echo "--- 玄鉴守护进程 ---"
if [ -f "/vol2/1000/AI专用/AgentOS-IsoSand/同构沙盘/data/daemon.pid" ]; then
    VERIFY_PID=$(cat "/vol2/1000/AI专用/AgentOS-IsoSand/同构沙盘/data/daemon.pid")
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
