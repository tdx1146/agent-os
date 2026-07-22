import subprocess
import sys

result = subprocess.run(
    [sys.executable, r"c:\Users\dandan\Desktop\小说\应如是论文\crack_zip.py"],
    capture_output=True,
    text=True
)

output = result.stdout + result.stderr
print(output)

with open(r"c:\Users\dandan\Desktop\小说\应如是论文\output.txt", "w", encoding="utf-8") as f:
    f.write(output)
