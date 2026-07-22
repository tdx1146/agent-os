#!/usr/bin/env python3
"""
文件保存日志 — log_file_save

从 edit-web.py 拆分，需要调用方传入 FILE_CHANGE_DIR。
"""

import os
import json
import difflib
import time


def log_file_save(path, new_content, is_novel, file_change_dir, old_content=None):
    """记录文件保存事件：读取旧内容 → 计算 diff → 写日志"""
    today = time.strftime('%Y-%m-%d')
    ts = time.time()
    ts_fmt = time.strftime('%Y-%m-%d %H:%M:%S')

    log_dir = os.path.join(file_change_dir, today)
    os.makedirs(log_dir, exist_ok=True)

    if old_content is None:
        old_content = ''
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    old_content = f.read()
            except Exception:
                old_content = ''

    old_size = len(old_content)
    new_size = len(new_content)

    diff_text = ''
    diff_lines = 0
    if old_content != new_content:
        try:
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            diff = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile='a/' + os.path.basename(path),
                tofile='b/' + os.path.basename(path),
                n=3
            ))
            diff_text = ''.join(diff)
            diff_lines = len(diff)
        except Exception:
            diff_text = '(diff failed)'

    entry = {
        "ts": ts,
        "time": ts_fmt,
        "path": path,
        "old_size": old_size,
        "new_size": new_size,
        "delta": new_size - old_size,
        "diff_lines": diff_lines,
        "is_novel": is_novel,
        "ext": os.path.splitext(path)[1],
    }

    is_small = new_size <= 51200
    if is_small or is_novel:
        entry["diff"] = diff_text[:10000]
        if len(diff_text) > 10000:
            entry["diff_truncated"] = True
    else:
        entry["diff"] = f"[large file, {diff_lines} lines changed]"
        if diff_text:
            entry["diff_preview"] = diff_text[:500]

    try:
        log_path = os.path.join(log_dir, 'changes.jsonl')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass

    try:
        delta = new_size - old_size
        delta_str = f"+{delta}" if delta > 0 else (str(delta) if delta < 0 else "0")
        icon = '📖' if is_novel else '📄'
        summary_line = f"[{ts_fmt}] {icon} {path} ({old_size}→{new_size}B, {delta_str})\n"
        summary_path = os.path.join(file_change_dir, 'today.log')
        with open(summary_path, 'a', encoding='utf-8') as f:
            f.write(summary_line)
    except Exception:
        pass
