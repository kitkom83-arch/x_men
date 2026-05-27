@echo off
setlocal
cd /d "%~dp0"

echo BN9 X Social Real V6 Easy Ready
echo.

if not exist ".env" (
  if exist ".env.example" (
    copy ".env.example" ".env" >nul
    echo Created .env from .env.example
  )
)

py -3 --version >nul 2>&1
if errorlevel 1 (
  python --version >nul 2>&1
  if errorlevel 1 (
    echo Python not found. Please run FIX_INSTALL.bat or install Python.
    pause
    exit /b 1
  )
  set "PYTHON_CMD=python"
) else (
  set "PYTHON_CMD=py -3"
)

echo Running offline health check...
%PYTHON_CMD% health_check.py --offline

echo.
echo Opening app...
%PYTHON_CMD% app.py

pause
