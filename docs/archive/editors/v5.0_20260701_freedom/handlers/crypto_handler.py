# handlers/crypto_handler.py — 加解密操作
# 每个函数接收 handler (HTTP handler实例) 作为第一个参数

import sys
import json
import os

_M = None
def g(name): return getattr(_M, name, None) if _M else None

def handle_encrypt_status(handler):
    """查询加密状态 (GET /api/encrypt-status)"""
    try:
        folder_name = handler._get_param('folder', 'encrypted')
        folder = g('_get_encrypt_folder')(folder_name)
        password = handler._get_param('password', '')

        files = sorted([f for f in os.listdir(folder) if f.endswith('.md')])

        # 判断是否已加密（只看文件格式，不需要密码）
        is_encrypted = g('_is_folder_encrypted')(folder) if files else False

        file_info = []
        for f in files:
            fpath = os.path.join(folder, f)
            sz = os.path.getsize(fpath)
            file_info.append({"name": f, "size": sz})

        session_decrypted = folder_name in g('SESSION_DECRYPTED')
        has_password = bool(g('PASSWORD_VAULT').get(folder_name))
        password_saved = folder_name in g('PASSWORD_VAULT')
        handler._send_json(200, {
            "ok": True,
            "folder": folder,
            "file_count": len(files),
            "files": file_info,
            "is_encrypted": is_encrypted,
            "session_decrypted": session_decrypted,
            "has_password": has_password,
            "password_saved": password_saved,
        })
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_encrypt(handler):
    """加密文件夹 (POST /api/encrypt)"""
    try:
        body = json.loads(handler.rfile.read(int(handler.headers.get('Content-Length', 0))))
        folder_name = body.get('folder', 'encrypted')
        password = body.get('password', '')
        save_password = body.get('save_password', False)

        if not password:
            handler._send_json(200, {"ok": False, "error": "密码不能为空"})
            return

        folder = g('_get_encrypt_folder')(folder_name)
        files = sorted([f for f in os.listdir(folder) if f.endswith('.md')])

        if not files:
            handler._send_json(200, {"ok": False, "error": "文件夹中没有 .md 文件"})
            return

        _xor_crypt = g('_xor_crypt')
        _xor_decrypt = g('_xor_decrypt')
        _is_hex_encrypted = g('_is_hex_encrypted')
        PASSWORD_VAULT = g('PASSWORD_VAULT')
        SESSION_DECRYPTED = g('SESSION_DECRYPTED')

        # 获取已保存的密码用于解密已加密文件
        saved_password = PASSWORD_VAULT.get(folder_name)
        
        # 加密所有文件
        encrypted_count = 0
        for f in files:
            fpath = os.path.join(folder, f)
            with open(fpath, 'r', encoding='utf-8') as fh:
                file_content = fh.read()
            
            # 如果文件已加密，先解密再重新加密
            if _is_hex_encrypted(file_content):
                decrypted_str = None
                # 优先用已保存的密码（旧密码），保证能正确解密
                if saved_password:
                    d = _xor_decrypt(file_content.strip(), saved_password)
                    decrypted_str = d
                else:
                    # 无已保存密码，尝试用用户输入的密码
                    d = _xor_decrypt(file_content.strip(), password)
                    if d:
                        decrypted_str = d
                
                if decrypted_str is not None:
                    file_content = decrypted_str
                # 如果都失败，就把当前内容当明文处理
            
            encrypted = _xor_crypt(file_content, password)
            with open(fpath, 'w', encoding='utf-8') as fh:
                fh.write(encrypted)
            encrypted_count += 1

        # 更新密码保险箱
        if save_password:
            PASSWORD_VAULT[folder_name] = password

        # 加密后清除 session 解密状态
        SESSION_DECRYPTED.discard(folder_name)

        handler._send_json(200, {
            "ok": True,
            "folder": folder,
            "encrypted_count": encrypted_count,
            "password_saved": save_password,
        })
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_decrypt(handler):
    """解密并返回内容 (POST /api/decrypt) — 不写盘，仅供查看"""
    try:
        body = json.loads(handler.rfile.read(int(handler.headers.get('Content-Length', 0))))
        folder_name = body.get('folder', 'encrypted')
        password = body.get('password', '')
        file_name = body.get('file', '')  # 可选，指定单个文件

        PASSWORD_VAULT = g('PASSWORD_VAULT')
        SESSION_DECRYPTED = g('SESSION_DECRYPTED')
        _get_encrypt_folder = g('_get_encrypt_folder')
        _is_folder_encrypted = g('_is_folder_encrypted')
        _is_hex_encrypted = g('_is_hex_encrypted')
        _xor_decrypt = g('_xor_decrypt')

        if not password:
            # 尝试从保险箱取密码
            if folder_name in PASSWORD_VAULT:
                password = PASSWORD_VAULT[folder_name]

        folder = _get_encrypt_folder(folder_name)
        
        # 检查是否需要密码：如果文件未加密，直接读明文
        files_in_folder = sorted([f for f in os.listdir(folder) if f.endswith('.md')])
        needs_password = False
        if password and files_in_folder:
            needs_password = _is_folder_encrypted(folder, password)
        elif files_in_folder:
            # 没给密码时，检查文件是不是hex格式
            sample_file = os.path.join(folder, files_in_folder[0])
            with open(sample_file, 'r', encoding='utf-8') as sf:
                sample = sf.read().strip()
            needs_password = _is_hex_encrypted(sample)
        
        if needs_password and not password:
            handler._send_json(200, {"ok": False, "error": "文件已加密，需要密码"})
            return

        if file_name:
            # 解密单个文件
            fpath = os.path.join(folder, file_name)
            if not os.path.exists(fpath):
                handler._send_json(200, {"ok": False, "error": f"文件不存在: {file_name}"})
                return
            # 先读文件，判断是否加密
            with open(fpath, 'r', encoding='utf-8') as fh:
                raw = fh.read()
            if _is_hex_encrypted(raw):
                if not password:
                    handler._send_json(200, {"ok": False, "error": "文件已加密，需要密码"})
                    return
                plain = _xor_decrypt(raw.strip(), password, check_magic=True)
                if not plain:
                    handler._send_json(200, {"ok": False, "error": "密码错误，解密失败"})
                    return
            else:
                plain = raw  # 未加密，直接返回明文
            handler._send_json(200, {
                "ok": True,
                "file": file_name,
                "content": plain,
                "size": len(plain),
            })
            return  # ← 关键：防止继续执行到外面的 send_json

        # 解密所有文件，返回全部内容
        files = sorted([f for f in os.listdir(folder) if f.endswith('.md')])
        contents = {}
        for f in files:
            fpath2 = os.path.join(folder, f)
            with open(fpath2, 'r', encoding='utf-8') as fh2:
                raw2 = fh2.read()
            if _is_hex_encrypted(raw2):
                if not password:
                    handler._send_json(200, {"ok": False, "error": "部分文件已加密，需要密码"})
                    return
                plain2 = _xor_decrypt(raw2.strip(), password, check_magic=True)
                if not plain2:
                    handler._send_json(200, {"ok": False, "error": "密码错误，解密失败"})
                    return
                contents[f] = plain2
            else:
                contents[f] = raw2

        SESSION_DECRYPTED.add(folder_name)
        handler._send_json(200, {
            "ok": True,
            "files": contents,
            "file_count": len(files),
        })
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_encrypt_save_file(handler):
    """保存解密后的文件（明文写入，自动重加密）"""
    try:
        body = json.loads(handler.rfile.read(int(handler.headers.get('Content-Length', 0))))
        folder_name = body.get('folder', 'encrypted')
        file_name = body.get('file', '')
        text = body.get('text', '')
        password = body.get('password', '')

        if not file_name:
            handler._send_json(200, {"ok": False, "error": "文件名不能为空"})
            return
        if not password:
            handler._send_json(200, {"ok": False, "error": "密码不能为空"})
            return

        folder = g('_get_encrypt_folder')(folder_name)
        fpath = os.path.join(folder, os.path.basename(file_name))
        
        # 写明文
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(text)
        
        # 立即加密
        g('_encrypt_file')(fpath, password)
        
        handler._send_json(200, {
            "ok": True,
            "file": file_name,
            "size": len(text),
        })
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_pass_password(handler):
    """把密码传递给AI（注入到当前session）"""
    try:
        body = json.loads(handler.rfile.read(int(handler.headers.get('Content-Length', 0))))
        folder = body.get('folder', 'encrypted')
        password = body.get('password', '')
        
        if not password:
            handler._send_json(200, {"ok": False, "error": "密码为空"})
            return
        
        PASSWORD_VAULT = g('PASSWORD_VAULT')
        
        # 从密码保险箱取或直接用传入的密码
        pw = PASSWORD_VAULT.get(folder, password)
        
        # 构造消息注入session
        pwd_display = pw[:1] + '*' * (len(pw) - 1)
        msg = (f'[🔐 系统] 密码已传递。密码是「{pw}」。'
               f'你可以用这个密码解密 encrypted/ 文件夹中的文件。'
               f'调用 /api/decrypt 时传入 password={pwd_display} 和你想读的文件名。')
        
        sk, _sf = g('get_session_info')()
        inject_via_websocket = g('inject_via_websocket')
        ok = inject_via_websocket(session_key=sk, message=msg)
        handler._send_json(200, {"ok": ok, "note": f"密码已注入会话，AI现在知道密码"})
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_encrypt_folders(handler):
    """列举目录下的文件夹，支持层级展开（从 BROWSE_ROOT 开始导航）"""
    try:
        parent = handler._get_param('parent', '')
        root = g('BROWSE_ROOT')

        if parent:
            target_dir = os.path.normpath(os.path.join(root, parent))
            if not target_dir.startswith(root):
                handler._send_json(403, {"ok": False, "error": "越权访问"})
                return
        else:
            target_dir = root

        items = []
        for name in sorted(os.listdir(target_dir)):
            fpath = os.path.join(target_dir, name)
            if os.path.isdir(fpath):
                has_subdirs = any(os.path.isdir(os.path.join(fpath, x)) for x in os.listdir(fpath))
                md_count = 0
                for dirpath, _, filenames in os.walk(fpath):
                    for f in filenames:
                        if f.endswith('.md'):
                            md_count += 1
                rel_path = os.path.join(parent, name) if parent else name
                items.append({
                    "name": name,
                    "path": rel_path,
                    "md_count": md_count,
                    "has_children": has_subdirs,
                })
        handler._send_json(200, {"ok": True, "root": root, "parent": parent, "items": items})
    except PermissionError:
        handler._send_json(200, {"ok": True, "root": root, "parent": parent, "items": []})
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})

def handle_try_decrypt_file(handler):
    """尝试解密一个文件（通过 query 参数）"""
    try:
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(handler.path).query)
        path = qs.get('path', [''])[0]
        password = qs.get('pw', [''])[0]
        if not path or not password:
            handler._send_json(200, {"ok": False, "error": "需要 path 和 pw 参数"})
            return
        try:
            from Crypto.Cipher import AES
            from Crypto.Protocol.KDF import scrypt
            from Crypto.Random import get_random_bytes
            import base64
            with open(path, 'rb') as f:
                raw = f.read()
            if not raw.startswith(b'LSE'):
                handler._send_json(200, {"ok": False, "error": "非加密文件格式"})
                return
            data = json.loads(raw[3:].decode('utf-8'))
            salt = base64.b64decode(data['s'])
            nonce = base64.b64decode(data['n'])
            tag = base64.b64decode(data['t'])
            ciphertext = base64.b64decode(data['c'])
            key = scrypt(password.encode('utf-8'), salt, 32, N=2**14, r=8, p=1)
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            handler._send_json(200, {"ok": True, "content": plaintext.decode('utf-8')})
        except:
            handler._send_json(200, {"ok": False, "error": "解密失败，可能是密码错误"})
    except Exception as e:
        handler._send_json(500, {"ok": False, "error": str(e)})
