#!/bin/bash
# 启动事件总线调度器
# 用法: bash start_scheduler.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/data/scheduler.pid"
LOG_FILE="/tmp/agent_os_scheduler.log"

cd "$SCRIPT_DIR"

# 检查是否已在运行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[scheduler] 调度器已在运行 (PID: $OLD_PID)"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

export PYTHONUNBUFFERED=1
export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"

# Write a small runner script
cat > "$SCRIPT_DIR/.run_scheduler.py" << 'PYEOF'
import sys, time
sys.path.insert(0, '/vol2/1000/AI专用/Agent OS/iso-sand/src')
from task_scheduler import TaskScheduler
s = TaskScheduler(
    event_file='/vol2/1000/AI专用/Agent OS/iso-sand/data/event_bus.jsonl',
    operation_log='/vol2/1000/AI专用/Agent OS/iso-sand/data/operation_log.jsonl',
    tick_interval=30.0,
    tasks_file='/vol2/1000/AI专用/Agent OS/iso-sand/deploy/tasks.yaml',
)
s.start()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    s.stop()
PYEOF

nohup python3 "$SCRIPT_DIR/.run_scheduler.py" > "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"
echo "[scheduler] ✅ 调度器已启动 (PID: $PID)"
echo "[scheduler] 日志: $LOG_FILE"
