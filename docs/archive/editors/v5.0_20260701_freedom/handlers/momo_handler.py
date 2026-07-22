# handlers/momo_handler.py — 摸摸协议
# 每个函数接收 handler (HTTP handler实例) 作为第一个参数

import sys
import json
import os
import time
import traceback
from utils.config import path

_M = None
def g(name): return getattr(_M, name, None) if _M else None

def handle_momo(handler):
    """🌫️ 摸摸协议主入口
    
    从原 _handle_api('momo') 分支拆出。
    处理 sub_action: pack, inject_feeling, status, list_backups, restore_backup,
                     search_backups, read_facts, index_report, trigger_digest,
                     promote_assertions, thinking_on, thinking_off
    """
    try:
        length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(length)
        data = json.loads(body) if length else {}
        sub = data.get('sub_action', '')
        
        if sub == 'pack':
            _momo_pack = g('_momo_pack')
            result = _momo_pack()
        elif sub == 'inject_feeling':
            _t0 = time.time()
            get_session_info = g('get_session_info')
            _sandglass_log = g('_sandglass_log')
            inject_via_websocket = g('inject_via_websocket')
            sk, _ = get_session_info()
            _t1 = time.time()
            feeling = data.get('feeling', '')
            # 先落沙再 inject（确保截断前记忆已存）
            _sandglass_log(feeling, 'sister')
            result = inject_via_websocket(sk, feeling, bypass_lock=True)
            _t2 = time.time()
            print(f"[timing] inject: get_session={_t1-_t0:.3f}s total={_t2-_t0:.3f}s sk={sk}", file=sys.stderr)
            result['_timing'] = {'get_session': round(_t1-_t0, 3), 'inject': round(_t2-_t0, 3)}
        elif sub == 'status':
            _momo_status = g('_momo_status')
            result = _momo_status()
        elif sub == 'list_backups':
            handle_list_backups_simple = g('handle_list_backups_simple') if g('handle_list_backups_simple') else None
            if handle_list_backups_simple:
                result = handle_list_backups_simple(handler)
            else:
                from handlers.session_handler import handle_list_backups
                result = handle_list_backups(handler)
        elif sub == 'restore_backup':
            from handlers.session_handler import handle_restore_backup
            result = handle_restore_backup(handler)
        elif sub == 'search_backups':
            query = data.get('query', '')
            limit = int(data.get('limit', 5))
            _search_backups = g('_search_backups')
            result = _search_backups(query, limit=limit)
        elif sub == 'read_facts':
            # 直接读取 facts.dict.md 内容
            try:
                LIGHT_SMOKE_DIR = g('LIGHT_SMOKE_DIR')
                facts_path = os.path.join(LIGHT_SMOKE_DIR, 'memory', 'facts.dict.md')
                with open(facts_path, 'r', encoding='utf-8') as f:
                    rc = f.read()
                result = {"ok": True, "content": rc, "size": len(rc)}
            except Exception as e:
                result = {"ok": False, "error": str(e)}
        elif sub == 'index_report':
            _momo_index_report = g('_momo_index_report')
            result = _momo_index_report()
        elif sub == 'trigger_digest':
            # 手动触发消化循环 cron
            try:
                r = subprocess.run(
                    ["openclaw", "cron", "run", "66e8fb9b-cbc6-4fd8-a62f-da4754cb8965"],
                    capture_output=True, text=True, timeout=60
                )
                if r.returncode == 0:
                    result = {"ok": True, "message": "消化循环已触发"}
                else:
                    result = {"ok": False, "error": r.stderr.strip() or r.stdout.strip()}
            except subprocess.TimeoutExpired:
                result = {"ok": False, "error": "触发超时"}
            except Exception as e:
                result = {"ok": False, "error": str(e)}
        elif sub == 'promote_assertions':
            _promote_pending_assertions = g('_promote_pending_assertions')
            result = _promote_pending_assertions()
        elif sub == 'thinking_on':
            try:
                r = subprocess.run(["openclaw", "agent", "--message", "/thinking high"], capture_output=True, text=True, timeout=15)
                result = {"ok": True, "message": "思考模式已开启"}
            except Exception as e:
                result = {"ok": False, "error": str(e)}
        elif sub == 'thinking_off':
            try:
                r = subprocess.run(["openclaw", "agent", "--message", "/thinking off"], capture_output=True, text=True, timeout=15)
                result = {"ok": True, "message": "思考模式已关闭"}
            except Exception as e:
                result = {"ok": False, "error": str(e)}
        else:
            result = {"ok": False, "error": f"未知摸摸操作: {sub}，可用: pack, inject_feeling, status, list_backups, restore_backup, search_backups, index_report, trigger_digest, thinking_on, thinking_off"}

        handler._send_json(200, result)
    except Exception as e:
        print(f"[EDIT WEB ERROR] /api/momo: {traceback.format_exc()}", file=sys.stderr)
        err = str(e)
        if 'Permission denied' in err:
            err = '无权限: ' + err.split(':')[-1].strip()
        handler._send_json(200, {"ok": False, "error": err})

def handle_pet_me(handler):
    """进入静默处理模式"""
    import subprocess as _sp
    
    summary_parts = []
    
    # 1. 执行内部处理
    try:
        mem_dir = os.path.join(g('LIGHT_SMOKE_DIR') or "", "memory")
        facts = os.path.join(mem_dir, "facts.dict.md")
        
        # 检查⏳断言
        pending = 0
        
        with open(facts, encoding='utf-8') as f:
            text = f.read()
        pending = text.count("| ⏳ |")
        summary_parts.append(f"⏳待升格: {pending}条")
        
        summary_parts.append("知识树已检查")
        
        # 2. 触发备份
        try:
            _sp.run(["python3", os.path.join(g('LIGHT_SMOKE_DIR') or "", "scripts", "momo-pack-cli.py")],
                   capture_output=True, timeout=30)
            summary_parts.append("备份完成")
        except:
            summary_parts.append("备份失败")
        
        # 写处理记录供监控使用
        try:
            with open(path('LAST_PROCESSING'), "w") as pf:
                pf.write("撸撸 " + __import__('datetime').datetime.now().strftime("%H:%M"))
        except:
            pass
        handler._send_json(200, {
            "ok": True,
            "summary": "\n".join(summary_parts)
        })
    except Exception as e:
        handler._send_json(200, {"ok": False, "error": str(e)})
