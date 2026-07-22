# handlers/inject_handler.py — 注入/编辑/子代理
# 每个函数接收 handler (HTTP handler实例) 作为第一个参数

import sys
import json
import os
import time
import subprocess
import traceback
from utils.config import path

_M = None
def g(name): return getattr(_M, name, None) if _M else None

def handle_inject(handler):
    """注入消息到当前会话"""
    try:
        length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(length)
        data = json.loads(body) if length else {}
        get_session_info = g('get_session_info')
        inject_via_websocket = g('inject_via_websocket')
        sk, _ = get_session_info()
        result = inject_via_websocket(sk, data['message'])
        handler._send_json(200, result)
    except Exception as e:
        err = str(e)
        if 'Permission denied' in err:
            err = '无权限: ' + err.split(':')[-1].strip()
        handler._send_json(200, {"ok": False, "error": err})

def handle_edit(handler):
    """截断编辑会话消息"""
    try:
        length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(length)
        data = json.loads(body) if length else {}
        get_session_info = g('get_session_info')
        edit_message = g('edit_message')
        sk, sf = get_session_info()
        result = edit_message(sf, data['index'], data['text'], approved=data.get('approved', False))
        handler._send_json(200, result)
    except Exception as e:
        err = str(e)
        if 'Permission denied' in err:
            err = '无权限: ' + err.split(':')[-1].strip()
        handler._send_json(200, {"ok": False, "error": err})

def handle_clear_lock(handler):
    """清除注入锁"""
    try:
        _cleanup_lock = g('_cleanup_lock')
        _cleanup_lock()
        handler._send_json(200, {"ok": True})
    except Exception as e:
        handler._send_json(200, {"ok": False, "error": str(e)})

def handle_pulse(handler):
    """发送保活脉冲"""
    try:
        length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(length)
        data = json.loads(body) if length else {}
        _send_pulse = g('_send_pulse')
        result = _send_pulse(data.get('mode'))
        handler._send_json(200, result)
    except Exception as e:
        handler._send_json(200, {"ok": False, "error": str(e)})

def handle_spawn_subagent(handler):
    """通过 Gateway RPC spawn 子代理"""
    try:
        data = json.loads(handler.rfile.read(int(handler.headers.get('Content-Length', 0))))
        task = data.get('task', '')
        model = data.get('model', 'GLM-Z1-Flash')
        _spawn_subagent_process = g('_spawn_subagent_process')
        result = _spawn_subagent_process(task, model)
        handler._send_json(200, result)
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_auth_subagent(handler):
    """通过 inject-helper 发送授权 RPC，允许当前设备 spawn 子代理"""
    try:
        get_session_info = g('get_session_info')
        GATEWAY_PORT = g('GATEWAY_PORT')
        GATEWAY_TOKEN = g('GATEWAY_TOKEN')
        OPENCLAW_HOME = g('OPENCLAW_HOME')
        IDENTITY_PATH = g('IDENTITY_PATH')
        
        sk, _ = get_session_info()
        if not sk:
            handler._send_json(200, {"ok": False, "error": "找不到 session"})
            return
        
        # RPC: 发起设备配对审批请求
        auth_rpc = json.dumps({
            "type": "req",
            "method": "device.requestApproval",
            "params": {
                "deviceId": "openclaw-control-ui",
                "displayName": "轻如烟编辑器",
            }
        })
        
        helper = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "inject-helper.mjs")
        env = os.environ.copy()
        env['GATEWAY_PORT'] = str(GATEWAY_PORT)
        env['GATEWAY_TOKEN'] = GATEWAY_TOKEN
        env['OPENCLAW_HOME'] = OPENCLAW_HOME
        env['OPENCLAW_IDENTITY_PATH'] = IDENTITY_PATH
        
        result = subprocess.run(
            [path('BUN_BIN'), helper, sk, auth_rpc],
            capture_output=True, text=True, timeout=30,
            env=env
        )
        if result.returncode == 0:
            handler._send_json(200, json.loads(result.stdout.strip()))
        else:
            handler._send_json(200, {"ok": False, "error": result.stderr[:300] or result.stdout[:300]})
    except Exception as e:
        handler._send_json(200, {"ok": False, "error": str(e)})

def handle_exec_subagent(handler):
    """执行 exec 子代理（直接调 API，不依赖 Gateway）"""
    try:
        data = json.loads(handler.rfile.read(int(handler.headers.get('Content-Length', 0))))
        task = data.get('task', '')
        model = data.get('model', 'deepseek-chat')
        if not task:
            handler._send_json(200, {"ok": False, "error": "需要 task 参数"})
            return
        _exec_subagent = g('_exec_subagent')
        result = _exec_subagent(task, model)
        handler._send_json(200, result)
    except Exception as e:
        handler._send_json(200, {"ok": False, "error": str(e)})

def handle_abort(handler):
    """停止 AI 思考（chat.abort）"""
    try:
        get_session_info = g('get_session_info')
        GATEWAY_PORT = g('GATEWAY_PORT')
        GATEWAY_TOKEN = g('GATEWAY_TOKEN')
        OPENCLAW_HOME = g('OPENCLAW_HOME')
        IDENTITY_PATH = g('IDENTITY_PATH')
        
        sk, _ = get_session_info()
        helper = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "inject-helper.mjs")
        proc = subprocess.run(
            [path('BUN_BIN'), helper, sk, "", "abort"],
            capture_output=True, text=True, timeout=15
        )
        result = json.loads(proc.stdout) if proc.stdout.strip() else {"ok": True}
        handler._send_json(200, result)
    except subprocess.TimeoutExpired:
        handler._send_json(200, {"ok": True, "note": "abort timeout (likely succeeded)"})
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_restart_http(handler):
    """重启 HTTP 服务器（向父进程发信号）"""
    try:
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json; charset=utf-8')
        handler.send_header('Access-Control-Allow-Origin', '*')
        handler.end_headers()
        resp = json.dumps({"ok": True, "note": "HTTP 服务器正在重启..."})
        handler.wfile.write(resp.encode())
    except:
        pass
    
    try:
        handler.wfile.flush()
        # 子进程等 1 秒后杀死当前进程再启动新进程
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(os.path.dirname(script_dir), os.path.basename(sys.modules.get('__main__', __import__('__main__')).__file__ if hasattr(sys.modules.get('__main__'), '__file__') else 'edit-web.py'))
        subprocess.Popen(
            ["sh", "-c",
             f"sleep 1 && kill -9 {os.getpid()} 2>/dev/null; cd '{os.path.dirname(script_path)}' && exec python3 '{script_path}'"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception as e:
        try:
            handler.send_response(500)
            handler.send_header('Content-Type', 'application/json; charset=utf-8')
            handler.end_headers()
            handler.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
        except:
            pass
