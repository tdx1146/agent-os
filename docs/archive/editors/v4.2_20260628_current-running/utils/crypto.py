#!/usr/bin/env python3
"""加密解密工具"""
import os

ENCRYPT_MAGIC = "🔐🔐🔐\\n"

def xor_crypt(text, password):
    result = []
    for i, c in enumerate(text):
        result.append(chr(ord(c) ^ ord(password[i % len(password)])))
    return "".join(result)

def xor_decrypt(hex_str, password, check_magic=True):
    try:
        raw = bytes.fromhex(hex_str).decode("utf-8")
        decrypted = xor_crypt(raw, password)
        if check_magic:
            if not decrypted.startswith(ENCRYPT_MAGIC):
                return None
            return decrypted[len(ENCRYPT_MAGIC):]
        return decrypted
    except:
        return None

def is_hex_encrypted(content):
    import re
    return bool(re.match(r"^[0-9a-fA-F]+$", content.strip())) and len(content.strip()) > 100

def encrypt_file(path, password):
    with open(path, "r", encoding="utf-8") as f:
        plain = f.read()
    encrypted = ENCRYPT_MAGIC + plain
    xored = xor_crypt(encrypted, password)
    hex_str = xored.encode("utf-8").hex()
    with open(path, "w", encoding="utf-8") as f:
        f.write(hex_str)

def decrypt_file_text(path, password):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return xor_decrypt(content, password)

def get_encrypt_folder(base_dir, folder_name="encrypted"):
    folder = os.path.join(base_dir, folder_name)
    os.makedirs(folder, exist_ok=True)
    return folder

def is_folder_encrypted(folder, password=None):
    test_file = os.path.join(folder, ".encrypted")
    if not os.path.exists(test_file):
        return False
    if password:
        content = xor_decrypt(open(test_file).read().strip(), password, check_magic=False)
        return content == "encrypted"
    return True
