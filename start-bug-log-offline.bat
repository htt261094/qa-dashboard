@echo off
rem Bug Log OFFLINE launcher - chay rieng phan Bug Log, KHONG dinh Jira, KHONG login.
rem Dung khi khong vao duoc VPN/Jira (vd mang nha). Double-click hoac chay trong terminal.
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem 1. Tim Python (py launcher hoac python)
set "PY="
where py >NUL 2>&1 && set "PY=py"
if not defined PY (
  where python >NUL 2>&1 && set "PY=python"
)
if not defined PY (
  echo [LOI] Chua co Python 3. Tai tai https://www.python.org/downloads/
  goto :end
)

rem 2. Cai requests neu thieu (Drive API dung requests)
%PY% -c "import requests" >NUL 2>&1
if errorlevel 1 (
  echo Dang cai thu vien requests...
  %PY% -m pip install requests
  if errorlevel 1 (
    echo [LOI] Cai requests that bai.
    goto :end
  )
)

rem 3. Lay port tu .env (mac dinh 8080)
set "PORT=8080"
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if /i "%%a"=="JIRA_PORT" set "PORT=%%b"
  )
)
set "PORT=!PORT: =!"

rem 4. Dong server cu dang chiem port
echo Dong server cu tren port !PORT! (neu co)...
powershell -NoProfile -Command "Get-NetTCPConnection -State Listen -LocalPort !PORT! -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

rem 5. Mo browser sau khi server kip bind
set "URL=http://localhost:!PORT!/bug-log"
echo Bug Log OFFLINE: !URL!   (Ctrl+C de dung server)
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process '!URL!'"

rem 6. Chay server - giu cua so mo cho den khi Ctrl+C
%PY% bug_log_offline.py

:end
echo.
echo === Server da dung. Nhan phim bat ky de dong cua so ===
pause
endlocal
