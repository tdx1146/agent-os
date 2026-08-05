#!/bin/bash
# 启动事件总线消费者
# 用法: bash start_consumer.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/data/consumer.pid"
LOG_FILE="/tmp/agent_os_consumer.log"

cd "$SCRIPT_DIR"

# 检查是否已在运行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[consumer] 消费者已在运行 (PID: $OLD_PID)"
        exit 0
    fi
    rm -f "$PID_FILE"
fi

export PYTHONUNBUFFERED=1
export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"

# Write a small runner script
cat > "$SCRIPT_DIR/.run_consumer.py" << 'PYEOF'
import sys, time
sys.path.insert(0, '/vol2/1000/AI专用/Agent OS/iso-sand/src')
from event_consumer import EventConsumer
c = EventConsumer(
    event_file='/vol2/1000/AI专用/Agent OS/iso-sand/data/event_bus.jsonl',
    seek_file='/vol2/1000/AI专用/Agent OS/iso-sand/data/event_bus.seek',
    rules_file='/vol2/1000/AI专用/Agent OS/iso-sand/deploy/event_rules.yaml',
    operation_log='/vol2/1000/AI专用/Agent OS/iso-sand/data/operation_log.jsonl',
    dead_letter='/vol2/1000/AI专用/Agent OS/iso-sand/data/.dead_letter_queue.jsonl',
    poll_interval=3.0
)
c.start()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    c.stop()
PYEOF

nohup python3 "$SCRIPT_DIR/.run_consumer.py" > "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"
echo "[consumer] ✅ 消费者已启动 (PID: $PID)"
echo "[consumer] 日志: $LOG_FILE"
