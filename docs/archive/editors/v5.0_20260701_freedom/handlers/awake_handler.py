# handlers/awake_handler.py — 守夜面板
# 每个函数接收 handler (HTTP handler实例) 作为第一个参数

import sys
import json
import os
import random
from utils.config import path

_M = None
def g(name): return getattr(_M, name, None) if _M else None

def handle_awake_questions(handler):
    """GET: 返回守夜问题库内容。POST: 保存修改后的内容。"""
    lib_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "唤醒题库.md")
    
    # 随机选一道题返回
    questions = []
    if os.path.exists(lib_path):
        try:
            with open(lib_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('q') and ' - ' in line:
                        questions.append(line)
        except:
            pass
    
    if questions:
        q = random.choice(questions)
        handler._send_json(200, {"ok": True, "question": q})
    else:
        handler._send_json(200, {"ok": False, "question": None, "note": "唤醒题库为空"})

def handle_awake_list(handler):
    """返回唤醒题库全部题目列表"""
    lib_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "唤醒题库.md")
    questions = []
    content_str = ""
    if os.path.exists(lib_path):
        try:
            with open(lib_path, 'r', encoding='utf-8') as f:
                content_str = f.read()
            for line in content_str.split('\n'):
                line = line.strip()
                if line.startswith('q') and ' - ' in line:
                    questions.append(line)
        except:
            pass
    handler._send_json(200, {
        "ok": True,
        "questions": questions,
        "total": len(questions),
        "file_content": content_str
    })

def handle_awake_save(handler):
    """保存唤醒题库内容"""
    lib_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "唤醒题库.md")
    try:
        length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(length)
        data = json.loads(body) if length else {}
        new_content = data.get('content', '')
        with open(lib_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        handler._send_json(200, {"ok": True, "note": f"已保存 ({len(new_content)} bytes)"})
    except Exception as e:
        err = str(e)
        if 'Permission denied' in err:
            err = '无权限: ' + err.split(':')[-1].strip()
        handler._send_json(200, {"ok": False, "error": err})

def handle_awake_send(handler):
    """dandan 操作的唤醒题库发送，绕过 inject 锁"""
    try:
        length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(length) if length else b'{}'
        data = json.loads(body)
        message = data.get('message', '')
        if not message.strip():
            handler._send_json(200, {"ok": False, "error": "消息为空"})
            return
        get_session_info = g('get_session_info')
        inject_via_websocket = g('inject_via_websocket')
        sk, _ = get_session_info()
        result = inject_via_websocket(sk, message, bypass_lock=True)
        handler._send_json(200, result)
    except Exception as e:
        err = str(e)
        if 'Permission denied' in err:
            err = '无权限: ' + err.split(':')[-1].strip()
        handler._send_json(200, {"ok": False, "error": err})

def handle_tts(handler):
    """TTS: 将文本转为语音 (POST /api/tts)，使用 edge-tts"""
    try:
        body_len = int(handler.headers.get('Content-Length', 0))
        body = json.loads(handler.rfile.read(body_len))
        text = body.get('text', '')
        if not text or not text.strip():
            handler._send_json(200, {"ok": False, "error": "empty text"})
            return
        import sys as _sys
        _sys.path.insert(0, path('SITE_PACKAGES'))
        import edge_tts
        import asyncio
        import base64
        import io
        async def _gen():
            tts = edge_tts.Communicate(text, voice='zh-CN-XiaoxiaoNeural')
            buf = io.BytesIO()
            async for chunk in tts.stream():
                if chunk['type'] == 'audio':
                    buf.write(chunk['data'])
            return buf.getvalue()
        audio_data = asyncio.run(_gen())
        audio_b64 = base64.b64encode(audio_data).decode()
        handler._send_json(200, {"ok": True, "audio": audio_b64, "format": "mp3"})
    except Exception as e:
        handler._send_json(200, {"ok": False, "error": str(e)})
