#!/usr/bin/env python3
"""
📂 文件浏览器 — 文件操作纯逻辑

从 edit-web.py 的 _handle_tb_xxx 方法中提取，自包含。
调用方传入所需路径参数。
"""

import os
import json
import time
import shutil
import zipfile
import xml.etree.ElementTree as ET


# ── 📋 列举文件 ─────────────────────────────────────────────────────

def list_folder_files(folder_path, extensions=('.md', '.docx', '.txt')):
    """列出文件夹下指定后缀的文件，含大小信息"""
    if not os.path.isdir(folder_path):
        return None, f"文件夹不存在: {folder_path}"
    files = sorted([
        f for f in os.listdir(folder_path)
        if f.endswith(extensions)
    ])
    file_info = []
    for f in files:
        fpath = os.path.join(folder_path, f)
        try:
            size = os.path.getsize(fpath)
            file_info.append({"name": f, "size": size, "size_kb": round(size / 1024, 1)})
        except OSError:
            file_info.append({"name": f, "size": 0, "size_kb": 0})
    return file_info, None


def list_subdirs(folder_path, md_ext='.md'):
    """列出子文件夹，含 .md 文件数量"""
    if not os.path.isdir(folder_path):
        return []
    subdirs = []
    for d in sorted(os.listdir(folder_path)):
        dpath = os.path.join(folder_path, d)
        if os.path.isdir(dpath) and not d.startswith('.'):
            try:
                md_count = len([f for f in os.listdir(dpath) if f.endswith(md_ext)])
            except OSError:
                md_count = 0
            subdirs.append({"name": d, "md_count": md_count, "path": dpath})
    return subdirs


def browse_root_dirs(root_path):
    """返回浏览根目录下的文件夹（含 .md 计数）"""
    if not os.path.isdir(root_path):
        return []
    items = []
    for d in sorted(os.listdir(root_path)):
        dpath = os.path.join(root_path, d)
        if os.path.isdir(dpath):
            try:
                md_count = len([f for f in os.listdir(dpath) if f.endswith('.md')])
            except OSError:
                md_count = 0
            items.append({'name': d, 'path': dpath, 'md_count': md_count})
    return items


# ── 📝 读文件 ───────────────────────────────────────────────────────

def read_text_file(path):
    """读取文本文件，自动 UTF-8/GBK 回退"""
    if not os.path.exists(path):
        return None, "文件不存在"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read(), None
    except UnicodeDecodeError:
        try:
            with open(path, 'r', encoding='gbk', errors='replace') as f:
                return f.read(), None
        except Exception as e:
            return None, str(e)
    except Exception as e:
        return None, str(e)


def read_docx_text(path):
    """从 .docx 提取纯文本"""
    try:
        with zipfile.ZipFile(path) as z:
            xml_content = z.read('word/document.xml')
            root = ET.fromstring(xml_content)
            ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            texts = []
            for t in root.iter(f'{ns}t'):
                if t.text:
                    texts.append(t.text)
            return '\n'.join(texts), None
    except Exception as e:
        return None, str(e)


# ── ✏️ 写文件 ───────────────────────────────────────────────────────

def save_file(path, content):
    """写入文件，返回旧内容（用于后续 diff 追踪）"""
    old_content = ''
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                old_content = f.read()
        except Exception:
            old_content = ''
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return old_content


def log_save_event(path, content, save_monitor_dir):
    """记录保存事件到 save.log"""
    try:
        log_line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] SAVED: {path} ({len(content)} bytes)\n"
        log_file = os.path.join(save_monitor_dir, 'save.log')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, 'a', encoding='utf-8') as lf:
            lf.write(log_line)
    except Exception:
        pass


def is_novel_path(path, novel_paths):
    """判断文件路径是否属于小说目录"""
    ap = os.path.abspath(path)
    for np_ in novel_paths:
        npa = os.path.abspath(np_)
        if ap.startswith(npa):
            return True
    return False


def log_file_change(path, new_content, is_novel, file_change_dir, old_content=None):
    """记录文件保存事件：计算 diff → 写日志到按日分目录"""
    import difflib
    today = time.strftime('%Y-%m-%d')
    ts_fmt = time.strftime('%Y-%m-%d %H:%M:%S')
    log_dir = os.path.join(file_change_dir, today)
    os.makedirs(log_dir, exist_ok=True)
    safe_name = os.path.basename(path).replace('/', '_').replace('\\', '_')
    log_path = os.path.join(log_dir, f"{safe_name}.diff.log")
    try:
        old = old_content if old_content is not None else ''
        diff = list(difflib.unified_diff(
            old.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f'a/{os.path.basename(path)}',
            tofile=f'b/{os.path.basename(path)}',
        ))
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"=== {ts_fmt} | {'novel' if is_novel else 'other'} | {len(new_content)}B | diff:{len(diff)} lines ===\n")
            if diff:
                f.write(''.join(diff[-20:]) + '\n')
    except Exception:
        pass


# ── 📁 创建/删除/重命名 ─────────────────────────────────────────────

def create_file_entry(folder, name, is_dir=False):
    """创建文件或目录。返回 (ok, message, path)"""
    fpath = os.path.join(folder, name)
    if is_dir:
        os.makedirs(fpath, exist_ok=True)
        return True, "目录已创建", fpath
    else:
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write('')
        return True, "文件已创建", fpath


def delete_file_entry(path):
    """删除文件或目录。返回 (ok, message)"""
    if not os.path.exists(path):
        return False, "文件不存在"
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
    return True, "删除成功"


def rename_file_entry(old_path, new_name, new_folder=''):
    """重命名或移动文件。返回 (ok, message, new_path)"""
    if not old_path or not new_name:
        return False, "需要 old_path 和 new_name 参数", None
    if '/' in new_name:
        return False, "名称不能包含路径分隔符", None
    dir_path = os.path.dirname(old_path)
    new_path = os.path.join(new_folder or dir_path, new_name)
    if os.path.exists(new_path):
        return False, "目标名称已存在", None
    os.rename(old_path, new_path)
    return True, "重命名成功", new_path
