@echo off
rem QA Dashboard launcher - Windows. Double-click hoac chay trong terminal.
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

rem 2. Kiem tra .env
if not exist ".env" (
  echo [LOI] Thieu file .env. Copy .env.example thanh .env roi dien JIRA_URL va JIRA_PAT.
  goto :end
)

rem 3. Cai requests neu thieu
%PY% -c "import requests" >NUL 2>&1
if errorlevel 1 (
  echo Dang cai thu vien requests...
  %PY% -m pip install requests
  if errorlevel 1 (
    echo [LOI] Cai requests that bai.
    goto :end
  )
)

rem 4. Lay port tu .env (mac dinh 8080) - chi doc JIRA_PORT, khong lo PAT
set "PORT=8080"
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
  if /i "%%a"=="JIRA_PORT" set "PORT=%%b"
)
set "PORT=!PORT: =!"

rem 5. Dong server cu dang chiem port (tranh port-in-use lam cua so dong)
echo Dong server cu tren port !PORT! (neu co)...
powershell -NoProfile -Command "Get-NetTCPConnection -State Listen -LocalPort !PORT! -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

rem 6. Mo browser sau khi server kip bind (chay nen)
set "URL=http://localhost:!PORT!/"
echo Dashboard: !URL!   (Ctrl+C de dung server)
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process '!URL!'"

rem 7. Chay server - giu cua so mo cho den khi Ctrl+C
%PY% qa_dashboard.py

:end
echo.
echo === Server da dung. Nhan phim bat ky de dong cua so ===
pause
endlocal