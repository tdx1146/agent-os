# handlers/helper_handler.py — 辅助功能
# 每个函数接收 handler (HTTP handler实例) 作为第一个参数

import sys
import json
import os
from urllib.parse import urlparse, parse_qs

_M = None
def g(name): return getattr(_M, name, None) if _M else None

def handle_memory_file_get(handler):
    """读取记忆文件 (GET /api/memory-file?name=xxx.md)"""
    try:
        qs = parse_qs(urlparse(handler.path).query)
        names = qs.get('name', [])
        if not names:
            handler._send_json(200, {"ok": False, "error": "missing ?name= 参数"})
            return
        name = names[0]
        # 安全检查：只允许 memory 目录下的 .md 文件
        name = os.path.basename(name)
        if not name.endswith('.md'):
            handler._send_json(200, {"ok": False, "error": "只允许 .md 文件"})
            return
        LIGHT_SMOKE_DIR = g('LIGHT_SMOKE_DIR')
        mem_dir = os.path.join(LIGHT_SMOKE_DIR, "memory")
        fpath = os.path.join(mem_dir, name)
        if not os.path.exists(fpath):
            handler._send_json(200, {"ok": False, "error": f"文件不存在: {name}"})
            return
        with open(fpath, encoding='utf-8') as f:
            content = f.read()
        handler._send_json(200, {
            "ok": True,
            "content": content,
            "path": fpath,
            "size": len(content),
        })
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_memory_file_list(handler):
    """列出所有记忆文件 (GET /api/memory-files)"""
    from datetime import datetime
    try:
        LIGHT_SMOKE_DIR = g('LIGHT_SMOKE_DIR')
        mem_dir = os.path.join(LIGHT_SMOKE_DIR, "memory")
        files = []
        if os.path.exists(mem_dir):
            for f in sorted(os.listdir(mem_dir)):
                if f.endswith('.md') and not f.startswith('.'):
                    fpath = os.path.join(mem_dir, f)
                    sz = os.path.getsize(fpath)
                    files.append({
                        "name": f,
                        "size": f"{sz/1024:.1f}KB" if sz > 1024 else f"{sz}B",
                        "modified": datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%m-%d %H:%M"),
                    })
        handler._send_json(200, {"ok": True, "files": files})
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_memory_file_save(handler):
    """保存记忆文件 (POST /api/memory-file)"""
    try:
        body = json.loads(handler.rfile.read(int(handler.headers['Content-Length'])))
        name = body.get('name', '')
        content = body.get('content', '')
        name = os.path.basename(name)
        if not name.endswith('.md'):
            handler._send_json(200, {"ok": False, "error": "只允许 .md 文件"})
            return
        LIGHT_SMOKE_DIR = g('LIGHT_SMOKE_DIR')
        mem_dir = os.path.join(LIGHT_SMOKE_DIR, "memory")
        fpath = os.path.join(mem_dir, name)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        handler._send_json(200, {
            "ok": True,
            "path": fpath,
            "size": len(content),
        })
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_secretary_log(handler):
    """📋 秘书观察日志 API"""
    LIGHT_SMOKE_DIR = g('LIGHT_SMOKE_DIR')
    log_path = os.path.join(LIGHT_SMOKE_DIR, 'memory', '秘书观察.log')
    try:
        with open(log_path, encoding='utf-8') as f:
            lines = f.readlines()
        recent = lines[-10:] if len(lines) > 10 else lines
        handler._send_json(200, {"ok": True, "total": len(lines), "recent": [l.strip() for l in recent]})
    except:
        handler._send_json(200, {"ok": True, "total": 0, "recent": []})

def handle_facts_stale_check(handler):
    """检查 facts.dict.md 是否过时 + 断言新鲜度"""
    import subprocess, datetime
    LIGHT_SMOKE_DIR = g('LIGHT_SMOKE_DIR')
    script = os.path.join(LIGHT_SMOKE_DIR, 'scripts', 'check-facts-stale.sh')
    if not os.path.exists(script):
        handler._send_json(200, {"ok": False, "error": "检查脚本不存在"})
        return
    try:
        result = subprocess.run(['bash', script, '--json'], capture_output=True, text=True, timeout=10)
        try:
            d = json.loads(result.stdout.strip())
            if 'stale_source' in d:
                d['stale'] = d['stale_source'] or d.get('stale_dep', False)
                d['files'] = d.get('source_files', [])
                d['dep_files'] = d.get('dep_files', [])
        except json.JSONDecodeError:
            d = {
                "ok": True,
                "stale": result.returncode == 2,
                "files": [],
                "detail": result.stdout.strip()
            }
        
        # Append assertion freshness check
        facts_path = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'facts.dict.md')
        assertion_ok = True
        assertion_msg = ""
        now = datetime.datetime.now()
        try:
            with open(facts_path, encoding='utf-8') as f:
                content = f.read()
            lines = content.split('\n')
            # Count assertions with confidence markers
            conf_count = sum(1 for l in lines if '✅' in l or '⏳' in l or '❌' in l)
            # Find last section change (## or #)
            last_update_line = 0
            for i, l in enumerate(lines):
                if l.startswith('## ') or l.startswith('# '):
                    last_update_line = i
            # Check if facts has automated section (added tonight)
            has_auto_section = any('自动化体系' in l or '子代理运营规则' in l for l in lines)
            assertion_ok = conf_count > 0 or has_auto_section
            assertion_msg = f"断言{conf_count}条{'含置信度' if conf_count > 0 else '🆕新结构'}"
        except:
            assertion_ok = False
            assertion_msg = "无法读取 facts.dict.md"
        
        d['assertions'] = {
            "ok": assertion_ok,
            "count": sum(1 for _ in []),
            "msg": assertion_msg
        }
        d['stale'] = d['stale'] or not assertion_ok
        
        handler._send_json(200, d)
    except Exception as e:
        handler._send_json(200, {"ok": False, "error": str(e)})

def handle_reminders(handler):
    """📋 提醒系统 API"""
    if handler.command == 'GET':
        _secretary_remind = g('_secretary_remind')
        pending = _secretary_remind()
        handler._send_json(200, {"ok": True, "reminders": pending, "count": len(pending)})
    elif handler.command == 'POST':
        try:
            data = json.loads(handler.rfile.read(int(handler.headers.get('Content-Length', 0))))
            action = data.get('action', 'add')
            if action == 'add':
                _add_reminder = g('_add_reminder')
                r = _add_reminder(
                    text=data.get('text', ''),
                    assignee=data.get('assignee', ''),
                    trigger_hint=data.get('trigger_hint', '')
                )
                handler._send_json(200, {"ok": True, "reminder": r})
            elif action == 'done':
                _load_reminders = g('_load_reminders')
                _save_reminders = g('_save_reminders')
                reminders = _load_reminders()
                rid = data.get('id')
                found = None
                for r in reminders:
                    if r.get('id') == rid:
                        r['done'] = not r.get('done', False)  # toggle
                        found = r
                        break
                _save_reminders(reminders)
                handler._send_json(200, {"ok": True, "done": found['done'] if found else False})
            elif action == 'clear_done':
                _load_reminders = g('_load_reminders')
                _save_reminders = g('_save_reminders')
                reminders = _load_reminders()
                reminders = [r for r in reminders if not r.get('done')]
                _save_reminders(reminders)
                handler._send_json(200, {"ok": True, "remaining": len(reminders)})
            else:
                handler._send_json(200, {"ok": False, "error": f"未知动作: {action}"})
        except Exception as e:
            handler._send_json(200, {"ok": False, "error": str(e)})

def handle_read_facts(handler):
    """读取 memory/facts.dict.md 内容"""
    LIGHT_SMOKE_DIR = g('LIGHT_SMOKE_DIR')
    facts_path = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'facts.dict.md')
    if not os.path.exists(facts_path):
        handler._send_json(200, {"ok": False, "error": "事实字典文件不存在"})
        return
    try:
        with open(facts_path, 'r', encoding='utf-8') as f:
            content = f.read()
        handler._send_json(200, {"ok": True, "content": content, "size": len(content)})
    except Exception as e:
        handler._send_json(200, {"ok": False, "error": str(e)})
