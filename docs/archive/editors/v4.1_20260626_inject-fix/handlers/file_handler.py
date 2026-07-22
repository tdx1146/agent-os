# handlers/file_handler.py — 文件操作
# 每个函数接收 handler (HTTP handler实例) 作为第一个参数

import sys
import json
import os
from urllib.parse import urlparse, parse_qs

_M = None
def g(name): return getattr(_M, name, None) if _M else None

def handle_tb_files(handler):
    """工具栏文件浏览：列出指定文件夹下的 .md 文件"""
    try:
        qs = parse_qs(urlparse(handler.path).query)
        folder = qs.get('folder', [''])[0]
        if not folder:
            handler._send_json(200, {"ok": False, "error": "需要 folder 参数"})
            return
        BROWSE_ROOT = g('BROWSE_ROOT')
        list_folder_files = g('list_folder_files')
        folder_path = os.path.join(BROWSE_ROOT, folder)
        files, err = list_folder_files(folder_path, ('.md',))
        if err:
            handler._send_json(200, {"ok": False, "error": err})
            return
        handler._send_json(200, {"ok": True, "folder": folder, "files": files, "file_count": len(files)})
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_tb_read_file(handler):
    """工具栏文件浏览：直接读取文件内容"""
    try:
        qs = parse_qs(urlparse(handler.path).query)
        path = qs.get('path', [''])[0]
        password = qs.get('pw', [''])[0]
        if not path:
            handler._send_json(200, {"ok": False, "error": "需要 path 参数"})
            return
        if password:
            _try_decrypt_file_handler = g('_try_decrypt_file')
            if _try_decrypt_file_handler:
                result = _try_decrypt_file_handler(path, password)
            else:
                # 内联 try_decrypt
                try:
                    from Crypto.Cipher import AES
                    from Crypto.Protocol.KDF import scrypt
                    import base64
                    with open(path, 'rb') as f:
                        raw = f.read()
                    if raw.startswith(b'LSE'):
                        data = json.loads(raw[3:].decode('utf-8'))
                        salt = base64.b64decode(data['s'])
                        nonce = base64.b64decode(data['n'])
                        tag = base64.b64decode(data['t'])
                        ciphertext = base64.b64decode(data['c'])
                        key = scrypt(password.encode('utf-8'), salt, 32, N=2**14, r=8, p=1)
                        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                        result = cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8')
                    else:
                        result = None
                except:
                    result = None
            if result:
                handler._send_json(200, {"ok": True, "content": result})
                return
        read_text_file = g('read_text_file')
        read_docx_text = g('read_docx_text')
        if path.endswith('.docx'):
            text, err = read_docx_text(path)
            if err:
                handler._send_json(200, {"ok": True, "content": f"[docx 读取失败: {err}]"})
            else:
                handler._send_json(200, {"ok": True, "content": text, "note": "docx 文本提取，格式可能简化"})
            return
        text, err = read_text_file(path)
        if err:
            handler._send_json(200, {"ok": False, "error": err})
            return
        handler._send_json(200, {"ok": True, "content": text})
    except FileNotFoundError:
        handler._send_json(200, {"ok": False, "error": "文件不存在"})
    except Exception as e:
        handler._send_json(200, {"ok": False, "error": str(e)})

def handle_tb_save_file(handler):
    """保存文件"""
    try:
        data = json.loads(handler.rfile.read(int(handler.headers.get('Content-Length', 0))))
        path = data.get('path', '')
        content = data.get('content', '')
        if not path:
            handler._send_json(200, {"ok": False, "error": "需要 path 参数"})
            return
        save_file = g('save_file')
        old_content = save_file(path, content)
        log_save_event = g('log_save_event')
        SAVE_MONITOR_DIR = g('SAVE_MONITOR_DIR')
        is_novel_path_fn = g('is_novel_path')
        NOVEL_PATHS = g('NOVEL_PATHS')
        log_file_change = g('log_file_change')
        FILE_CHANGE_DIR = g('FILE_CHANGE_DIR')
        secretary_analyze_save = g('secretary_analyze_save')
        LIGHT_SMOKE_DIR = g('LIGHT_SMOKE_DIR')
        log_save_event(path, content, SAVE_MONITOR_DIR)
        try:
            is_novel = is_novel_path_fn(path, NOVEL_PATHS)
            log_file_change(path, content, is_novel, FILE_CHANGE_DIR, old_content)
        except Exception:
            pass
        try:
            secretary_analyze_save(path, content, old_content, LIGHT_SMOKE_DIR)
        except Exception:
            pass
        handler._send_json(200, {"ok": True, "message": "保存成功"})
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_tb_create_file(handler):
    """创建文件/目录"""
    try:
        data = json.loads(handler.rfile.read(int(handler.headers.get('Content-Length', 0))))
        folder = data.get('folder', '')
        name = data.get('name', '')
        is_dir = data.get('is_dir', False)
        if not folder or not name:
            handler._send_json(200, {"ok": False, "error": "需要 folder 和 name 参数"})
            return
        create_file_entry = g('create_file_entry')
        ok, msg, fpath = create_file_entry(folder, name, is_dir)
        handler._send_json(200, {"ok": ok, "message": msg, "path": fpath})
    except Exception as e:
        err = str(e)
        if 'Permission denied' in err:
            err = '无权限: ' + err.split(':')[-1].strip()
        handler._send_json(200, {"ok": False, "error": err})

def handle_tb_delete_file(handler):
    """删除文件/目录"""
    try:
        data = json.loads(handler.rfile.read(int(handler.headers.get('Content-Length', 0))))
        path = data.get('path', '')
        if not path:
            handler._send_json(200, {"ok": False, "error": "需要 path 参数"})
            return
        delete_file_entry = g('delete_file_entry')
        ok, msg = delete_file_entry(path)
        handler._send_json(200, {"ok": ok, "message": msg})
    except Exception as e:
        err = str(e)
        if 'Permission denied' in err:
            err = '无权限: ' + err.split(':')[-1].strip()
        handler._send_json(200, {"ok": False, "error": err})

def handle_tb_rename_file(handler):
    """重命名/移动文件"""
    try:
        body_len = int(handler.headers.get('Content-Length', 0))
        raw_body = handler.rfile.read(body_len)
        data = json.loads(raw_body)
        old_path = data.get('old_path', '')
        new_name = data.get('new_name', '')
        new_folder = data.get('new_folder', '')
        rename_file_entry = g('rename_file_entry')
        ok, msg, new_path = rename_file_entry(old_path, new_name, new_folder)
        handler._send_json(200, {"ok": ok, "message": msg, "new_path": new_path})
    except Exception as e:
        err = str(e)
        if 'Permission denied' in err:
            err = '无权限: ' + err.split(':')[-1].strip()
        handler._send_json(200, {"ok": False, "error": err})

def handle_list_files(handler):
    """列出指定文件夹下的 .md 文件"""
    try:
        qs = parse_qs(urlparse(handler.path).query)
        if 'path' in qs:
            folder_path = qs.get('path', [''])[0]
            folder_name = os.path.basename(folder_path)
        else:
            folder_name = qs.get('folder', [''])[0]
            if not folder_name:
                handler._send_json(200, {"ok": False, "error": "需要 folder 或 path 参数"})
                return
            LIGHT_SMOKE_DIR = g('LIGHT_SMOKE_DIR')
            folder_path = os.path.join(LIGHT_SMOKE_DIR, folder_name)
        list_folder_files = g('list_folder_files')
        list_subdirs = g('list_subdirs')
        files, err = list_folder_files(folder_path)
        if err:
            if 'Permission denied' in str(err):
                handler._send_json(200, {"ok": False, "error": f"无权限: {folder_path}"})
                return
            handler._send_json(200, {"ok": False, "error": err})
            return
        subdirs = list_subdirs(folder_path)
        handler._send_json(200, {
            "ok": True, "folder": folder_name, "folder_path": folder_path,
            "files": files, "file_count": len(files), "items": subdirs,
        })
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_browse_dirs(handler):
    """返回浏览根目录下的文件夹"""
    try:
        BROWSE_ROOT = g('BROWSE_ROOT')
        browse_root_dirs = g('browse_root_dirs')
        items = browse_root_dirs(BROWSE_ROOT)
        handler._send_json(200, {"ok": True, "root": BROWSE_ROOT, "items": items})
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})
