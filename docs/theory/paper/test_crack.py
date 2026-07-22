import zipfile
import sys

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

print("=" * 60)
print("ZIP Password Cracker")
print("=" * 60)
print(f"Target: {ZIP_PATH}")
print()

# Check zip file
zf = zipfile.ZipFile(ZIP_PATH, 'r')
info_list = zf.infolist()
print("Files in zip:")
for info in info_list:
    print(f"  {info.filename} ({info.file_size} bytes)")
    print(f"    Flag bits: {info.flag_bits:#06x}")
    if info.flag_bits & 0x1:
        print(f"    ENCRYPTED: Yes")
zf.close()

# Try passwords
found = False
for pwd in PASSWORDS:
    print(f"Trying password: {pwd!r}")
    for enc in ['utf-8', 'cp437', 'gbk']:
        try:
            zf = zipfile.ZipFile(ZIP_PATH, 'r')
            pwd_bytes = pwd.encode(enc)
            zf.setpassword(pwd_bytes)
            with zf.open(TARGET_FILE, 'r') as f:
                data = f.read(100)
            zf.close()
            print(f"*** SUCCESS! Password found: {pwd!r} (encoding={enc}) ***")
            found = True
            break
        except:
            zf.close()
            pass
    if found:
        break
    print("  FAILED")

if not found:
    print("None of the passwords worked.")
