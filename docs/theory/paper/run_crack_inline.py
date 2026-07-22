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

output_lines = []

output_lines.append("=" * 60)
output_lines.append("ZIP Password Cracker - Dictionary Attack")
output_lines.append("=" * 60)
output_lines.append(f"Target: {ZIP_PATH}")
output_lines.append("")

# Check zip file
try:
    zf = zipfile.ZipFile(ZIP_PATH, 'r')
    info_list = zf.infolist()
    output_lines.append("Files in zip:")
    for info in info_list:
        output_lines.append(f"  {info.filename} ({info.file_size} bytes)")
        output_lines.append(f"    Flag bits: {info.flag_bits:#06x}")
        if info.flag_bits & 0x1:
            output_lines.append(f"    ENCRYPTED: Yes")
    zf.close()
except Exception as e:
    output_lines.append(f"ERROR: {e}")

# Try passwords
found = False
for pwd in PASSWORDS:
    output_lines.append(f"Trying password: {pwd!r}")
    for enc in ['utf-8', 'cp437', 'gbk']:
        try:
            zf = zipfile.ZipFile(ZIP_PATH, 'r')
            pwd_bytes = pwd.encode(enc)
            zf.setpassword(pwd_bytes)
            with zf.open(TARGET_FILE, 'r') as f:
                data = f.read(100)
            zf.close()
            output_lines.append(f"*** SUCCESS! Password found: {pwd!r} (encoding={enc}) ***")
            output_lines.append(f"First 100 bytes preview: {data[:100]}")
            found = True
            break
        except Exception as e:
            zf.close()
    if found:
        break
    output_lines.append("  FAILED")

if not found:
    output_lines.append("None of the passwords worked.")

# Write output
output = '\n'.join(output_lines)
with open(r"c:\Users\dandan\Desktop\小说\应如是论文\output.txt", "w", encoding="utf-8") as f:
    f.write(output)

print(output)
