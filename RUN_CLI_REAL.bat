@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv call FIX_INSTALL.bat
.venv\Scripts\python.exe cli_listen.py --queries queries.txt --max-posts 10 --telegram
pause
