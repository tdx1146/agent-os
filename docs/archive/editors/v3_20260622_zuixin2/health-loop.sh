#!/bin/bash
# health-loop.sh — 自愈循环，每5分钟检查 edit-web.py (:18888)
# 用法：nohup bash health-loop.sh &
LOG="/tmp/pulse-status.json"
EDITOR_DIR="/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts"

while true; do
    TS=$(date '+%Y-%m-%d %H:%M:%S')
    
    # 检查 18888 是否活着
    if ! curl -sf http://127.0.0.1:18888 > /dev/null 2>&1; then
        echo "[$TS] ❌ edit-web 挂了 → 尝试重启" >> "$LOG"
        cd "$EDITOR_DIR"
        python3 edit-web.py 2>&1 &
        echo "[$TS] ✅ 已重启 (PID $!)" >> "$LOG"
    else
        echo "[$TS] ✅ edit-web 正常" >> "$LOG"
    fi
    
    sleep 300  # 5分钟
done
