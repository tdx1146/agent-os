#!/bin/bash
# 启动事件总线消费者
# 用法: bash start_consumer.sh
# 2026-08-10 部署统一化：路径/日志从 Agent OS/env.local 读取，缺失时相对推导

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_OS_HOME="$(cd "$SCRIPT_DIR/.." && pwd)"
# 加载统一配置（env.local），缺失则相对推导
if [ -f "$AGENT_OS_HOME/env.local" ]; then
    set -a; . "$AGENT_OS_HOME/env.local"; set +a
fi
LOG_DIR="${LOG_DIR:-$AGENT_OS_HOME/logs}"
mkdir -p "$LOG_DIR"

PID_FILE="$SCRIPT_DIR/data/consumer.pid"
LOG_FILE="$LOG_DIR/consumer.log"

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

# 生成运行器（路径随 SCRIPT_DIR 推导，换机器自动适配，无硬编码）
cat > "$SCRIPT_DIR/.run_consumer.py" << PYEOF
import sys, time
sys.path.insert(0, '$SCRIPT_DIR/src')
from event_consumer import EventConsumer
c = EventConsumer(
    event_file='$SCRIPT_DIR/data/event_bus.jsonl',
    seek_file='$SCRIPT_DIR/data/event_bus.seek',
    rules_file='$SCRIPT_DIR/deploy/event_rules.yaml',
    operation_log='$SCRIPT_DIR/data/operation_log.jsonl',
    dead_letter='$SCRIPT_DIR/data/.dead_letter_queue.jsonl',
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
