#!/bin/bash
# edit-web 监督：挂了自动重启
while true; do
  if ! curl -s -o /dev/null http://127.0.0.1:18888/ --connect-timeout 5 2>/dev/null; then
    echo "$(date): edit-web 挂了，正在重启" >> /tmp/edit-web-watchdog.log
    cd /vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟 && nohup python3 scripts/edit-web.py > /tmp/edit-web-restart.log 2>&1 &
    echo "$(date): 已重启 PID=$!" >> /tmp/edit-web-watchdog.log
  fi
  sleep 30
done
