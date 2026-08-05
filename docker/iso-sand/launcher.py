#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iso-sand 容器双进程启动器（Phase 7 / Agent OS Docker 化）
============================================================
在单一容器内以子进程方式运行 scheduler + consumer（与裸进程模式同构：
裸模式由 start_scheduler.sh / start_consumer.sh 各起一个进程）。

设计取舍：
  - 单容器双进程（而非两个服务）：scheduler 与 consumer 强耦合于同一数据目录
    与配置；consumer 崩溃时总线会积压，scheduler 单独存在无意义，双双重启
    是正确的恢复语义。compose restart: unless-stopped 保证拉起。
  - 任一子进程退出 → 本启动器 exit(2) → 容器退出 → compose 重启整容器。
  - 维护 /tmp/iso_sand_alive 心跳文件（每 20s 更新），供 compose healthcheck
    探测「双进程均存活」。
  - 路径全部由环境变量驱动（ISO_SAND_DATA_DIR / ISO_SAND_TASKS_FILE /
    ISO_SAND_RULES_FILE），沙箱验证与生产切换零代码改动。
"""

import os
import subprocess
import sys
import time

SRC = "/app/iso-sand/src"
DATA_DIR = os.environ.get("ISO_SAND_DATA_DIR", "/app/iso-sand/data")
TASKS_FILE = os.environ.get(
    "ISO_SAND_TASKS_FILE", "/app/iso-sand/deploy/tasks.yaml")
RULES_FILE = os.environ.get(
    "ISO_SAND_RULES_FILE", "/app/iso-sand/deploy/event_rules.yaml")

ALIVE_FILE = "/tmp/iso_sand_alive"
HEARTBEAT_EVERY = 20.0  # 秒


def _env() -> dict:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = SRC + (":" + existing if existing else "")
    return env


def _write_runner(path: str, body: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


def _scheduler_runner() -> str:
    return f'''import sys, time
sys.path.insert(0, {SRC!r})
from task_scheduler import TaskScheduler
s = TaskScheduler(
    event_file={os.path.join(DATA_DIR, "event_bus.jsonl")!r},
    operation_log={os.path.join(DATA_DIR, "operation_log.jsonl")!r},
    tick_interval=30.0,
    tasks_file={TASKS_FILE!r},
)
s.start()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    s.stop()
'''


def _consumer_runner() -> str:
    return f'''import sys, time
sys.path.insert(0, {SRC!r})
from event_consumer import EventConsumer
c = EventConsumer(
    event_file={os.path.join(DATA_DIR, "event_bus.jsonl")!r},
    seek_file={os.path.join(DATA_DIR, "event_bus.seek")!r},
    rules_file={RULES_FILE!r},
    operation_log={os.path.join(DATA_DIR, "operation_log.jsonl")!r},
    dead_letter={os.path.join(DATA_DIR, ".dead_letter_queue.jsonl")!r},
    poll_interval=3.0,
)
c.start()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    c.stop()
'''


def main() -> int:
    os.makedirs(DATA_DIR, exist_ok=True)
    env = _env()

    sched_runner = _write_runner("/tmp/run_scheduler.py", _scheduler_runner())
    cons_runner = _write_runner("/tmp/run_consumer.py", _consumer_runner())

    # stdout 继承容器 stdout（docker logs 可见子进程日志）
    procs = {
        "scheduler": subprocess.Popen(
            [sys.executable, sched_runner], env=env),
        "consumer": subprocess.Popen(
            [sys.executable, cons_runner], env=env),
    }

    print(f"[iso-launcher] scheduler={procs['scheduler'].pid} "
          f"consumer={procs['consumer'].pid}")
    print(f"[iso-launcher] DATA_DIR={DATA_DIR}")
    print(f"[iso-launcher] TASKS_FILE={TASKS_FILE}")
    print(f"[iso-launcher] RULES_FILE={RULES_FILE}")

    last_beat = 0.0
    try:
        while True:
            dead = [name for name, p in procs.items() if p.poll() is not None]
            if dead:
                for name in dead:
                    print(f"[iso-launcher] ❌ {name} 退出 rc={procs[name].returncode}（日志见上方 docker logs）")
                return 2

            now = time.time()
            if now - last_beat >= HEARTBEAT_EVERY:
                with open(ALIVE_FILE, "w", encoding="utf-8") as f:
                    f.write(f"{now}\n")
                last_beat = now
            time.sleep(5)
    except KeyboardInterrupt:
        for p in procs.values():
            p.terminate()
        return 0


if __name__ == "__main__":
    sys.exit(main())
