#!/bin/bash
# 干净的编辑器启动脚本
# 用途：停止所有守护脚本并启动编辑器的 web 服务
# 创建：2026-06-26
#
# 用法：
#   bash start-clean.sh

set -e

SCRIPT_DIR="/vol1/@team/qh团队/QH/AI专用/所有自动化/轻如烟/scripts"
cd "$SCRIPT_DIR"

echo "[1/3] 停止所有守护脚本..."
pkill -f watchdog.sh 2>/dev/null || true
pkill -f health-loop.sh 2>/dev/null || true
pkill -f health-check.sh 2>/dev/null || true

echo "[2/3] 释放端口 18888..."
kill -9 $(lsof -ti :18888) 2>/dev/null || true
sleep 2

echo "[3/3] 启动编辑器..."
nohup python3 edit-web.py > /tmp/edit-web-clean.log 2>&1 &
PID=$!
echo "编辑器已启动 PID=$PID"

# 等待 5 秒验证
sleep 5
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18888/ 2>/dev/null || echo "FAIL")
echo "HTTP 状态: $HTTP_CODE"
echo "日志: tail -f /tmp/edit-web-clean.log"

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ 编辑器启动成功"
else
    echo "❌ 编辑器启动失败，检查日志: tail -f /tmp/edit-web-clean.log"
fi
