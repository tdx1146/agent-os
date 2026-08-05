#!/usr/bin/env python3
"""
heartbeat.py — 主总线心跳任务（Phase 2 / D6）
=============================================
由 task_scheduler 按 tasks.yaml 调度执行（每 5 分钟），
向主总线写入一条 sandglass.heartbeat 事件（v1.1 契约），证明调度器存活。

事件契约（v1.1）: schema_version / event_id / event_type / producer / result / trace_id
通过 LogWriter 写入（线程+进程锁），与调度器/消费者同源安全。
"""

import os
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta

_BJT = timezone(timedelta(hours=8))

# 自身定位（deploy/）→ iso-sand 根
_HERE = os.path.dirname(os.path.abspath(__file__))
_ISO_SAND_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ISO_SAND_ROOT, "src"))

from log_writer import LogWriter  # noqa: E402


def main() -> int:
    event = {
        "t": datetime.now(_BJT).isoformat(),
        "schema_version": "1.1",
        "event_id": str(uuid.uuid4()),
        "event_type": "sandglass.heartbeat",
        "producer": "task_scheduler/heartbeat",
        "result": "OK",
        "trace_id": f"heartbeat-{int(time.time())}",
        "detail": "调度器心跳：调度器存活证明（每 5 分钟）",
    }
    bus_file = os.path.join(_ISO_SAND_ROOT, "data", "event_bus.jsonl")
    LogWriter(bus_file).write(event)
    print(f"[heartbeat] ✅ 心跳事件已写入: {event['event_id']} "
          f"trace={event['trace_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
