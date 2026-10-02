# Tu chay QA Dashboard luc dang nhap Windows (Decision #99).
#
# ASCII-only co chu dich: Windows PowerShell 5.1 doc .ps1 KHONG-BOM theo ANSI -> ky tu
# tieng Viet co dau pha parser.
#
# Tao 2 Scheduled Task cho user hien tai:
#   "QA Dashboard"        - at logon: pythonw qa_dashboard.py (an, khong cua so console).
#                           Log -> reports\dashboard.log. Chet thi tu restart (3 lan / 1 phut).
#   "QA Dashboard Window" - at logon + tre 20s: mo Edge/Chrome che do --app (cua so rieng).
# Kem shortcut "QA Dashboard" tren Desktop (mo cua so app bat ky luc nao).
#
# PHAI CHAY TRONG TERMINAL CUA BAN (khong qua Claude Code - container MSIX):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_autostart.ps1
# Go bo:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_autostart.ps1 -Uninstall
# Tuy chon: -NoWindow (chi chay server, khong tu mo cua so) -Python <duong dan pythonw.exe>

param([switch]$Uninstall, [switch]$NoWindow, [string]$Python = '')

$ErrorActionPreference = 'Stop'
$TASK_SRV = 'QA Dashboard'
$TASK_WIN = 'QA Dashboard Window'
$ROOT = Split-Path -Parent $PSScriptRoot
$LNK = Join-Path ([Environment]::GetFolderPath('Desktop')) 'QA Dashboard.lnk'

if ($Uninstall) {
  foreach ($t in @($TASK_SRV, $TASK_WIN)) {
    if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
      Unregister-ScheduledTask -TaskName $t -Confirm:$false
      Write-Output "Da go task: $t"
    }
  }
  if (Test-Path $LNK) { Remove-Item $LNK -Force; Write-Output "Da xoa shortcut: $LNK" }
  exit 0
}

# --- Python: uu tien pythonw.exe (khong bat console). KHONG dung stub WindowsApps. ---
if (-not $Python) {
  $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue |
         Where-Object { $_.Source -notmatch 'WindowsApps' } | Select-Object -First 1
  if ($cmd) { $Python = $cmd.Source }
}
if (-not $Python -or -not (Test-Path $Python)) {
  Write-Error "Khong tim thay pythonw.exe. Truyen -Python 'C:\...\pythonw.exe'."
}

# --- Port tu .env (mac dinh 8080). Chi doc JIRA_PORT, khong in gi khac trong .env. ---
$PORT = '8080'
$envFile = Join-Path $ROOT '.env'
if (Test-Path $envFile) {
  $line = Select-String -Path $envFile -Pattern '^\s*JIRA_PORT\s*=' | Select-Object -First 1
  if ($line) { $PORT = ($line.Line -split '=', 2)[1].Trim().Trim('"').Trim("'") }
}
# PHAI la localhost (khong 127.0.0.1): Google OAuth chi nhan redirect URI da dang ky (#96).
$URL = "http://localhost:$PORT/"

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

# --- Task 1: server ---
$trg = New-ScheduledTaskTrigger -AtLogOn -User $user
$act = New-ScheduledTaskAction -Execute $Python -Argument "`"$ROOT\qa_dashboard.py`"" -WorkingDirectory $ROOT
Register-ScheduledTask -TaskName $TASK_SRV -Action $act -Trigger $trg -Settings $settings `
  -Principal $principal -Description "QA Dashboard server ($URL)" -Force | Out-Null
Write-Output "Da dang ky task: $TASK_SRV  ($Python)"

# --- Trinh duyet che do app (Edge co san tren Windows; Chrome neu co) ---
$browser = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
  "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if ($browser) {
  $sh = New-Object -ComObject WScript.Shell
  $s = $sh.CreateShortcut($LNK)
  $s.TargetPath = $browser
  $s.Arguments = "--app=$URL"
  $s.WorkingDirectory = $ROOT
  $s.Description = 'QA Dashboard'
  $s.Save()
  Write-Output "Da tao shortcut: $LNK"
} else {
  Write-Output 'Khong tim thay Edge/Chrome - bo qua shortcut + cua so tu mo.'
}

# --- Task 2: tu mo cua so app sau khi server kip bind ---
if ($browser -and -not $NoWindow) {
  $trg2 = New-ScheduledTaskTrigger -AtLogOn -User $user
  $trg2.Delay = 'PT20S'
  $act2 = New-ScheduledTaskAction -Execute $browser -Argument "--app=$URL"
  Register-ScheduledTask -TaskName $TASK_WIN -Action $act2 -Trigger $trg2 -Settings $settings `
    -Principal $principal -Description 'Mo cua so QA Dashboard luc dang nhap' -Force | Out-Null
  Write-Output "Da dang ky task: $TASK_WIN"
} elseif (Get-ScheduledTask -TaskName $TASK_WIN -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskName $TASK_WIN -Confirm:$false
}

# --- Chay ngay khong can logout. Server cu (start.bat) dang giu port thi task se chet vi
#     port-in-use -> dong server cu truoc. ---
$busy = Get-NetTCPConnection -State Listen -LocalPort $PORT -ErrorAction SilentlyContinue
if ($busy) {
  Write-Output "Port $PORT dang co server chay (PID $($busy[0].OwningProcess)) - giu nguyen, task se chay tu lan logon sau."
} else {
  Start-ScheduledTask -TaskName $TASK_SRV
  Write-Output "Da start server. Log: $ROOT\reports\dashboard.log"
}
Write-Output "Mo: $URL"
