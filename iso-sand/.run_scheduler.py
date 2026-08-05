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
