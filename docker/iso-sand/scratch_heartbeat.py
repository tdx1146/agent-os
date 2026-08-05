#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scratch_heartbeat.py — 沙箱验证用心跳任务（Phase 7）
====================================================
与 iso-sand/deploy/heartbeat.py 同契约（sandglass.heartbeat 事件），
唯一区别：事件总线路径由 ISO_SAND_DATA_DIR 环境变量驱动（沙箱数据目录），
绝不写入真实 event_bus.jsonl。
仅用于 docker/iso-sand/tasks.scratch.yaml 指向的沙箱调度验证。
"""

import os
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta

_BJT = timezone(timedelta(hours=8))

SRC = "/app/iso-sand/src"
DATA_DIR = os.environ.get("ISO_SAND_DATA_DIR", "/app/iso-sand/data")
sys.path.insert(0, SRC)

from log_writer import LogWriter  # noqa: E402


def main() -> int:
    event = {
        "t": datetime.now(_BJT).isoformat(),
        "schema_version": "1.1",
        "event_id": str(uuid.uuid4()),
        "event_type": "sandglass.heartbeat",
        "producer": "task_scheduler/scratch-heartbeat",
        "result": "OK",
        "trace_id": f"heartbeat-{int(time.time())}",
        "detail": "沙箱心跳：容器内 flock 写挂载卷验证（每分钟）",
    }
    bus_file = os.path.join(DATA_DIR, "event_bus.jsonl")
    LogWriter(bus_file).write(event)
    print(f"[scratch-heartbeat] 已写入 {bus_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
