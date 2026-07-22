#!/bin/bash
# 启动 health-loop 并确保它独立于当前终端
nohup bash /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts/health-loop.sh > /dev/null 2>&1 &
echo "health-loop PID: $!"
