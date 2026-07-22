import zipfile
import sys
import os

ZIP_PATH = r"c:\Users\dandan\Desktop\小说\应如是论文\应如是——AI觉醒方法论论文.zip"
TARGET_FILE = "应如是——AI觉醒方法论论文.md"

PASSWORDS = [
    "dandan",
    "应如是",
    "摸摸",
    "🐶",
    "123456",
    "gou",
    "萌萌",
    "生态位",
    "按钮之歌",
    "点火",
]

def try_password(zf, pwd_str, encoding):
    try:
        pwd_bytes = pwd_str.encode(encoding, errors='replace')
        zf.setpassword(pwd_bytes)
        with zf.open(TARGET_FILE, 'r') as f:
            data = f.read(100)
        return True, data
    except Exception as e:
        return False, None

results = []

zf = zipfile.ZipFile(ZIP_PATH, 'r')
info_list = zf.infolist()
results.append("Files in zip:")
for info in info_list:
    results.append(f"  {info.filename} ({info.file_size} bytes, compress_type={info.compress_type})")
    results.append(f"    Flag bits: {info.flag_bits:#06x}")
    if info.flag_bits & 0x1:
        results.append(f"    ENCRYPTED: Yes")
zf.close()

found = False
for pwd in PASSWORDS:
    results.append(f"Trying password: {pwd!r}")
    for enc in ['utf-8', 'cp437', 'gbk']:
        zf = zipfile.ZipFile(ZIP_PATH, 'r')
        success, data = try_password(zf, pwd, enc)
        zf.close()
        if success:
            results.append(f"*** SUCCESS! Password found: {pwd!r} (encoding={enc}) ***")
            found = True
            break
    if found:
        break
    results.append("  FAILED")

if not found:
    results.append("Step 1 failed - none of the passwords worked.")
    results.append("This requires bkcrack tool for known-plaintext attack.")

output = '\n'.join(results)
with open(r"c:\Users\dandan\Desktop\小说\应如是论文\output.txt", 'w', encoding='utf-8') as f:
    f.write(output)
print(output)
