#!/usr/bin/env python3
"""
加密工具 — XOR 字节加密/解密（QY_ENC_V1 魔数验证）

从 edit-web.py 拆分，需要调用方传入 light_smoke_dir。
"""

import os

ENCRYPT_MAGIC = 'QY_ENC_V1'
PASSWORD_VAULT = {}
SESSION_DECRYPTED = set()


def xor_crypt(text, password):
    """字节级 XOR 加密，加 magic 头，输出 hex。无 surrogate 问题"""
    pw = sum(ord(c) for c in password) & 0xFF
    data = (ENCRYPT_MAGIC + text).encode('utf-8')
    xored = bytes(b ^ pw for b in data)
    return xored.hex()


def xor_decrypt(hex_str, password, check_magic=True):
    """字节级 XOR 解密，验证 magic 头"""
    pw = sum(ord(c) for c in password) & 0xFF
    try:
        raw = bytes.fromhex(hex_str)
        decoded = bytes(b ^ pw for b in raw)
        plain = decoded.decode('utf-8')
        if check_magic:
            if plain.startswith(ENCRYPT_MAGIC):
                return plain[len(ENCRYPT_MAGIC):]
            return ''
        return plain
    except Exception:
        return ''


def is_hex_encrypted(content):
    """检查文件内容是否已加密（hex格式特征：不含空格换行以外的非hex字符）"""
    if not content or len(content) < 10:
        return False
    stripped = content.strip()
    valid_chars = all(c in '0123456789abcdefABCDEF \n\r\t' for c in stripped)
    return valid_chars


def encrypt_file(path, password):
    """加密单个文件，原地覆盖。已加密的文件会先解密再重新加密"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
    except UnicodeDecodeError:
        with open(path, 'r', encoding='gbk', errors='replace') as f:
            text = f.read()

    if is_hex_encrypted(text):
        decrypted = xor_decrypt(text.strip(), password, check_magic=False)
        content = decrypted if decrypted else text
    else:
        content = text

    encrypted = xor_crypt(content, password)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(encrypted)


def decrypt_file_text(path, password):
    """解密单个文件，返回明文（不写盘）"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
    except UnicodeDecodeError:
        with open(path, 'r', encoding='gbk', errors='replace') as f:
            text = f.read().strip()
    if not text:
        return ''
    result = xor_decrypt(text, password, check_magic=True)
    if not result:
        raise ValueError("密码错误")
    return result


def get_encrypt_folder(light_smoke_dir, folder_name="encrypted"):
    """获取加密文件夹路径。绝对路径直用，相对路径解析为轻如烟子目录。"""
    if os.path.isabs(folder_name):
        folder = folder_name
        os.makedirs(folder, exist_ok=True)
    else:
        folder = os.path.join(light_smoke_dir, folder_name)
        os.makedirs(folder, exist_ok=True)
    return folder


def is_folder_encrypted(folder, password=None):
    """检查文件夹是否已加密（只看原始文件格式，不需要密码）"""
    files = sorted([f for f in os.listdir(folder) if f.endswith('.md')])
    if not files:
        return False
    try:
        first = os.path.join(folder, files[0])
        with open(first, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content:
            return False
        return is_hex_encrypted(content)
    except:
        return False
