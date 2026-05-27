@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo สร้าง Windows Task Scheduler ชื่อ BN9_X_SOCIAL_REAL_V5 เวลา 09:00 ทุกวัน
schtasks /Create /SC DAILY /TN "BN9_X_SOCIAL_REAL_V5" /TR "\"%~dp0RUN_CLI_REAL.bat\"" /ST 09:00 /F
pause
