#!/usr/bin/env python3
"""
文本工具函数 — strip_metadata, group_into_pairs, xml_escape, is_novel_path

从 edit-web.py 拆分，自包含。
"""

import re
import os


def strip_metadata(text):
    """Strip untrusted metadata blocks from message content."""
    if not text:
        return text
    lines = text.split("\n")
    clean = []
    skip_block = False
    for line in lines:
        if line.startswith("Sender (untrusted metadata):") or \
           line.startswith("System:") or \
           line.startswith("```json"):
            skip_block = True
            continue
        if skip_block:
            if line.strip() == "```":
                skip_block = False
                continue
            if line.startswith("[") and line.endswith("]"):
                continue
            continue
        if not skip_block:
            clean.append(line)
    result = "\n".join(clean)
    result = re.sub(r'^\[.*?\]\s*', '', result, flags=re.MULTILINE)
    result = re.sub(r'\{[^}]*"label"[^}]*\}', '', result)
    return result.strip()


def group_into_pairs(messages):
    """Group messages into user-assistant pairs, skipping toolResult."""
    pairs = []
    current_user = None
    current_assistants = []

    for m in messages:
        role = m["role"]
        if role == "toolResult":
            continue
        if role == "user":
            if current_user is not None:
                pairs.append({"user": current_user, "assistants": current_assistants})
            current_user = m
            current_assistants = []
        elif role == "assistant":
            current_assistants.append(m)

    if current_user is not None:
        pairs.append({"user": current_user, "assistants": current_assistants})

    return pairs


def xml_escape(s):
    """XML转义"""
    s = s.replace('&', '&amp;')
    s = s.replace('<', '&lt;')
    s = s.replace('>', '&gt;')
    s = s.replace('"', '&quot;')
    s = s.replace("'", '&apos;')
    return s


def is_novel_path(path, novel_paths):
    """判断文件路径是否属于小说目录"""
    ap = os.path.abspath(path)
    for np_ in novel_paths:
        npa = os.path.abspath(np_)
        if ap.startswith(npa):
            return True
    return False
