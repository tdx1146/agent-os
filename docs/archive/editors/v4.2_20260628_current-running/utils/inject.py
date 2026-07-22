#!/usr/bin/env python3
"""
WS注入 + 锁管理
"""
import json, os, subprocess, time

INJECT_LOCK_TTL = 20
MAX_EDIT_DEPTH = 1
_locks = {}

THIS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def inject_via_websocket(session_key, message, bypass_lock=False):
    now = time.time()
    if not bypass_lock:
        lock_ts = _locks.get(session_key)
        if lock_ts and now - lock_ts < INJECT_LOCK_TTL:
            raise Exception("安全限制：上一轮已注入过，请在下一轮用户消息后再试")
    _locks[session_key] = now
    helper = os.path.join(THIS_DIR, "inject-helper.mjs")
    result = subprocess.run(
        ["/var/apps/bunjs/target/bin/bun", helper, session_key, message],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        raise Exception(f"inject-helper 失败: {result.stderr.strip() or result.stdout.strip()}")
    return json.loads(result.stdout.strip())

def cleanup_lock():
    now = time.time()
    expired = [k for k, v in _locks.items() if now - v >= INJECT_LOCK_TTL]
    for k in expired:
        _locks.pop(k, None)

def get_lock(session_key):
    return _locks.get(session_key)
