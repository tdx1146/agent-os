#!/usr/bin/env python3
"""
提醒管理 — load_reminders, save_reminders, add_reminder
守夜问题 — load_night_questions, pick_night_question

从 edit-web.py 拆分，自包含。
"""

import os
import json
import random
import datetime


# ── 提醒 ────────────────────────────────────────────────────────────────

def load_reminders(light_smoke_dir):
    """加载提醒列表"""
    fp = os.path.join(light_smoke_dir, 'memory', 'reminders.json')
    try:
        with open(fp, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def save_reminders(reminders, light_smoke_dir):
    """保存提醒列表"""
    fp = os.path.join(light_smoke_dir, 'memory', 'reminders.json')
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


# ── 守夜问题库 ────────────────────────────────────────────────────────

NIGHT_WATCH_LIB = None


def load_night_questions(script_dir):
    """从守夜问题库.md 加载问题列表"""
    global NIGHT_WATCH_LIB
    if NIGHT_WATCH_LIB is not None:
        return NIGHT_WATCH_LIB

    lib_path = os.path.join(script_dir, "唤醒题库.md")
    if not os.path.exists(lib_path):
        return []

    questions = []
    with open(lib_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('q') and ' - ' in line:
                try:
                    parts = line.split(' - ', 1)
                    qid_tag = parts[0].strip()
                    q_text = parts[1].strip()
                    cat = ""
                    if '#' in qid_tag:
                        cat = qid_tag.split('#', 1)[1] if '#' in qid_tag else ""
                    questions.append({
                        "id": qid_tag.split(':')[0] if ':' in qid_tag else qid_tag,
                        "category": cat,
                        "text": q_text,
                        "full": f"{qid_tag} - {q_text}"
                    })
                except:
                    pass

    NIGHT_WATCH_LIB = questions
    return questions


def pick_night_question(script_dir):
    """随机选一个守夜问题"""
    questions = load_night_questions(script_dir)
    if not questions:
        return None
    return random.choice(questions)
