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
