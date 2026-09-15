@echo off
setlocal EnableExtensions
title DeskTrack Agent Installer

echo.
echo  DeskTrack Agent — employee PC setup
echo  ===================================
echo.

set "INSTALL_DIR=%LOCALAPPDATA%\DeskTrackAgent"
set "ZIP=%TEMP%\desktrack-agent.zip"
set "REPO_ZIP=https://github.com/ahl-official/employee-tracking/archive/refs/heads/main.zip"

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python 3 from https://www.python.org/downloads/
  echo Tick "Add python.exe to PATH", then run this installer again.
  pause
  exit /b 1
)

echo Installing to: %INSTALL_DIR%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo Downloading agent from GitHub...
powershell -NoProfile -Command ^
  "try { Invoke-WebRequest -Uri '%REPO_ZIP%' -OutFile '%ZIP%' -UseBasicParsing } catch { exit 1 }"
if errorlevel 1 (
  echo Download failed. Check internet access.
  pause
  exit /b 1
)

echo Extracting...
powershell -NoProfile -Command ^
  "Expand-Archive -Path '%ZIP%' -DestinationPath '%TEMP%\desktrack-src' -Force; ^
   Copy-Item -Path '%TEMP%\desktrack-src\employee-tracking-main\agent\*' -Destination '%INSTALL_DIR%' -Recurse -Force"

if not exist "%INSTALL_DIR%\desktrack_agent.py" (
  echo Could not find agent files after download.
  pause
  exit /b 1
)

echo.
set /p SERVER=Server URL [https://desktrack.hairscalptradingco.com]: 
if "%SERVER%"=="" set "SERVER=https://desktrack.hairscalptradingco.com"
set /p USERNAME=Your DeskTrack username: 
set /p PASSWORD=Your DeskTrack password: 

(
  echo [server]
  echo url = %SERVER%
  echo.
  echo [auth]
  echo username = %USERNAME%
  echo password = %PASSWORD%
  echo.
  echo [agent]
  echo camera_index = 0
  echo interval_seconds = 2.0
  echo auto_clock_in = true
) > "%INSTALL_DIR%\config.ini"

echo.
echo Installing Python packages...
python -m pip install --upgrade pip
python -m pip install -r "%INSTALL_DIR%\requirements.txt"
if errorlevel 1 (
  echo pip install failed.
  pause
  exit /b 1
)

echo.
echo Creating desktop shortcut...
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\DeskTrack Agent.lnk'); ^
   $s.TargetPath = 'python'; ^
   $s.Arguments = '\"%INSTALL_DIR%\desktrack_agent.py\"'; ^
   $s.WorkingDirectory = '%INSTALL_DIR%'; ^
   $s.Save()"

echo.
echo Done.
echo  1. Open https://desktrack.hairscalptradingco.com in Chrome
echo  2. Log in - My desk - click "Enroll face" (allow camera)
echo  3. Then start "DeskTrack Agent" from your Desktop
echo.
pause

cd /d "%INSTALL_DIR%"
python desktrack_agent.py
