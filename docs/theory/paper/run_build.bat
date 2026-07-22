@echo off
cd /d "c:\Users\dandan\Desktop\小说\应如是论文"
echo Step 1: Install python-docx...
"C:\Users\dandan\.workbuddy\binaries\python\versions\3.13.12\python.exe" -m pip install python-docx
echo.
echo Step 2: Run build...
"C:\Users\dandan\.workbuddy\binaries\python\versions\3.13.12\python.exe" build_docx.py
echo.
echo Exit code: %errorlevel%
pause
