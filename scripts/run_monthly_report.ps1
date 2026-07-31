# Bao cao Bug Metric thang -> CTO (Google Chat), chay OFFLINE tren Windows.
# Port Windows cua scripts/run_monthly_report.sh (macOS). Xem CLAUDE.md + monthly_reporter_chat_app.py.
#
# ASCII-only co chu dich: Windows PowerShell 5.1 doc .ps1 KHONG-BOM theo ANSI -> ky tu
# tieng Viet co dau se pha parser. Giu file nay thuan ASCII de chay on dinh qua Task Scheduler.
#
# Luong: dung bug_log_offline.py (doc cache Drive, KHONG can VPN/Jira) tren 1 PORT RIENG
# (ne server chinh 8080) -> doi /analytics 200 -> reporter export PDF + upload Drive + gui
# Google Chat cho CTO -> tat server. Scheduled Task goi script nay HANG NGAY; guard cuoi
# thang tu bo qua cac ngay khac (giong cron Mac). KHONG gui email.
#
# -Test: chay THU - bo guard cuoi thang + bo --cron => reporter gui vao space TEST
# (TEST_GOOGLECHAT_SPACE) chu KHONG phai space CTO. Dung de verify trigger bat ky luc nao.
#
# Log: script tu append reports\cron.log.

param([switch]$Test)

$ErrorActionPreference = 'Continue'

# PowerShell decode stdout cua native command theo [Console]::OutputEncoding (mac dinh OEM
# cp437/850) trong khi Python xuat UTF-8 -> log ra mojibake (Gß╗¡i...). Ep UTF-8 de doc duoc.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# --- Cau hinh (sua neu doi may) ---
$ROOT = 'C:\Users\tuant\Desktop\Work\qa-dashboard'
$PY   = 'C:\Users\tuant\AppData\Local\Programs\Python\Python312\python.exe'
$PORT = if ($env:REPORT_PORT) { $env:REPORT_PORT } else { '8077' }  # port rieng, ne 8080

Set-Location $ROOT
New-Item -ItemType Directory -Force -Path "$ROOT\reports" | Out-Null

# Bat buoc UTF-8 cho stdout/stderr cua Python. Khi Task Scheduler pipe output, Python lay
# codepage ANSI (cp1252) -> print tieng Viet raise UnicodeEncodeError va job chet TRUOC khi
# gui report (da dinh 2026-07-31, rc=1). Dat o day de ap cho ca server offline lan reporter.
$env:PYTHONUTF8       = '1'
$env:PYTHONIOENCODING = 'utf-8'

# Moi output -> reports\cron.log (Scheduled Task khong tu redirect nhu crontab).
$LOG = "$ROOT\reports\cron.log"
function Log($msg) {
  $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
  Write-Output $line
  Add-Content -Path $LOG -Value $line -Encoding utf8
}

$MODE = if ($Test) { 'TEST space' } else { 'REAL space (CTO)' }
Log "===== monthly report (offline, port $PORT, $MODE) ====="

# 1. Chi chay that vao ngay cuoi thang (mai la mung 1). Chan som de khong phi dung server.
#    Che do -Test bo qua guard nay (chay thu bat ky ngay nao).
if (-not $Test -and (Get-Date).AddDays(1).Day -ne 1) {
  Log "Hom nay khong phai ngay cuoi thang - bo qua."
  exit 0
}

# 2. Dung server bug-log OFFLINE tren port rieng. OFFLINE=1 de config khong bat Jira creds.
$env:OFFLINE   = '1'
$env:JIRA_PORT = $PORT
$srvOut = "$ROOT\reports\offline_server.log"
$srv = Start-Process -FilePath $PY -ArgumentList 'bug_log_offline.py' `
  -WorkingDirectory $ROOT -PassThru -WindowStyle Hidden `
  -RedirectStandardOutput $srvOut -RedirectStandardError "$srvOut.err"

# Reporter chay o config NON-offline (giong Mac: chi thua JIRA_PORT, KHONG thua OFFLINE).
Remove-Item Env:\OFFLINE -ErrorAction SilentlyContinue

$rc = 1
try {
  # 3. Doi /analytics tra 200 (toi da ~40s) - route reporter drive de export metric bug.
  $ready = $false
  for ($i = 0; $i -lt 40; $i++) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$PORT/analytics" -TimeoutSec 5
      if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    if ($srv.HasExited) { break }   # server chet som (thieu dep...) -> khoi doi du 40s
    Start-Sleep -Seconds 1
  }

  if (-not $ready) {
    Log "[LOI] bug_log_offline.py (/analytics) khong san sang tren port $PORT - bo qua gui. Xem $srvOut.err"
    exit 1
  }

  # 4. Reporter: export PDF + upload Drive + gui Google Chat. --cron tu guard ngay cuoi thang
  #    VA keo theo --real (space CTO). Che do -Test: khong truyen gi => space TEST.
  $repArgs = @('core\monthly_reporter_chat_app.py')
  if (-not $Test) { $repArgs += '--cron' }
  & $PY $repArgs 2>&1 | ForEach-Object { Log $_ }
  $rc = $LASTEXITCODE
  Log "===== xong (rc=$rc) ====="
}
finally {
  # Tat server offline du thoat kieu gi.
  if ($srv -and -not $srv.HasExited) {
    Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue
  }
}

exit $rc
