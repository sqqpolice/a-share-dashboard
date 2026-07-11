@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"

REM === A-SHARE SECTOR DASHBOARD LAUNCHER ===
REM Step 1: find python
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py"
if not defined PY (
    echo [ERROR] Python not found in PATH.
    echo Please install Python from https://www.python.org/ and check "Add Python to PATH".
    pause & exit /b 1
)

echo [1/3] Checking requests library ...
%PY% -c "import requests" >nul 2>nul || (
    echo Installing requests...
    %PY% -m pip install requests
)

echo [2/3] Fetching real-time data ...
%PY% fetch_a股.py

echo [3/3] Starting local server at http://localhost:8000/
%PY% fetch_a股.py --serve

pause
