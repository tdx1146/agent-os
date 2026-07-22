#!/usr/bin/env python3
"""
📋 秘书模块 — 文件变更追踪 + 提醒管理

从 edit-web.py 拆分，自包含。
需要调用方传入 light_smoke_dir。
"""

import os
import json
import datetime


# ── 提醒文件路径 ─────────────────────────────────────────────────────

def reminders_file(light_smoke_dir):
    return os.path.join(light_smoke_dir, 'memory', 'reminders.json')


def load_reminders(light_smoke_dir):
    """加载提醒列表"""
    fp = reminders_file(light_smoke_dir)
    try:
        with open(fp, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def save_reminders(reminders, light_smoke_dir):
    """保存提醒列表"""
    fp = reminders_file(light_smoke_dir)
    try:
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(reminders, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_reminder(text, light_smoke_dir, assignee="", trigger_hint=""):
    """添加一条提醒"""
    reminders = load_reminders(light_smoke_dir)
    reminders.append({
        "id": len(reminders) + 1,
        "text": text,
        "assignee": assignee,
        "trigger_hint": trigger_hint,
        "done": False,
        "created": datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    })
    save_reminders(reminders, light_smoke_dir)
    return reminders[-1]


def secretary_remind(light_smoke_dir):
    """📋 返回当前未完成的提醒摘要"""
    reminders = load_reminders(light_smoke_dir)
    return [r for r in reminders if not r.get('done')]


# ── 🔍 文件变更分析 ─────────────────────────────────────────────────

def secretary_analyze_save(path, new_content, old_content, light_smoke_dir):
    """🔍 小秘书静默分析：用户保存文件时异步分析变更"""
    # 只分析 .md 文件，且必须真的有变更
    if not path.endswith('.md') or new_content == old_content:
        return

    # 计算 diff 长度——太短的变更不分析
    old_lines = old_content.split('\n')
    new_lines = new_content.split('\n')
    if abs(len(new_lines) - len(old_lines)) < 2 and new_content.strip() == old_content.strip():
        return

    # 写一条轻量级追踪记录到 secretary log
    ts = datetime.datetime.now().strftime('%H:%M')
    fname = os.path.basename(path)
    added = len(new_lines) - len(old_lines)
    log_dir = os.path.join(light_smoke_dir, 'memory')
    log_path = os.path.join(log_dir, '秘书观察.log')
    try:
        os.makedirs(log_dir, exist_ok=True)
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{ts}] {fname} ({'+' if added >= 0 else ''}{added}行)\n")
    except Exception:
        pass
