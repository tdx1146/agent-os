"""注入锁管理

集中管理 inject 互斥锁，含 TTL 超时兜底。
"""

import os
import time

LOCK_TTL_SECONDS = 20  # 锁最长持有时间（A5 设置）


def get_lock_file(light_smoke_dir):
    """返回锁文件路径"""
    if not light_smoke_dir:
        return None
    lock_dir = os.path.join(light_smoke_dir, '.locks')
    os.makedirs(lock_dir, exist_ok=True)
    return os.path.join(lock_dir, '.inject_lock')


def cleanup_lock(light_smoke_dir, logger_fn=None):
    """清理注入锁文件（含 TTL 超时兜底）

    Args:
        light_smoke_dir: 项目根目录
        logger_fn: 可选的日志函数，接收字符串参数
    """
    lock_file = get_lock_file(light_smoke_dir)
    if not lock_file or not os.path.exists(lock_file):
        return

    try:
        mtime = os.path.getmtime(lock_file)
        age = time.time() - mtime
        if age > LOCK_TTL_SECONDS:
            os.remove(lock_file)
            msg = f"[锁超时] 锁文件超过 {LOCK_TTL_SECONDS}s（实际 {age:.0f}s），强制清除"
            if logger_fn:
                logger_fn(msg)
            return
    except (OSError, IOError):
        pass

    try:
        os.remove(lock_file)
    except (OSError, IOError):
        pass


def is_locked(light_smoke_dir):
    """检查是否被锁定"""
    lock_file = get_lock_file(light_smoke_dir)
    if not lock_file:
        return False
    return os.path.exists(lock_file)


def acquire_lock(light_smoke_dir, logger_fn=None):
    """尝试获取锁，返回 True 表示成功获取

    如果已存在锁且未超时，返回 False。
    已超时的过期锁会被自动清除并重新获取。
    """
    lock_file = get_lock_file(light_smoke_dir)
    if not lock_file:
        return False
    if os.path.exists(lock_file):
        try:
            mtime = os.path.getmtime(lock_file)
            if time.time() - mtime > LOCK_TTL_SECONDS:
                # 锁已过期，清除后继续往下走获取新锁
                os.remove(lock_file)
            else:
                return False  # 锁仍有效
        except (OSError, IOError):
            return False  # 无法检查，假定被锁定

    try:
        # 创建锁文件
        with open(lock_file, 'w') as f:
            f.write(str(time.time()))
        return True
    except (OSError, IOError):
        return False
