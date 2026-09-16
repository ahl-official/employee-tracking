@echo off
setlocal EnableExtensions
title DeskTrack Agent Installer

echo.
echo  DeskTrack Agent - employee PC setup
echo  ===================================
echo.

set "INSTALL_DIR=%LOCALAPPDATA%\DeskTrackAgent"
set "ZIP=%TEMP%\desktrack-agent.zip"
set "SRC=%TEMP%\desktrack-src"
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
if exist "%SRC%" rmdir /s /q "%SRC%"
if exist "%ZIP%" del /f /q "%ZIP%"

echo Downloading agent from GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%REPO_ZIP%' -OutFile '%ZIP%' -UseBasicParsing"
if errorlevel 1 (
  echo Download failed. Check internet access.
  pause
  exit /b 1
)

echo Extracting...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%SRC%' -Force; Copy-Item -Path '%SRC%\employee-tracking-main\agent\*' -Destination '%INSTALL_DIR%' -Recurse -Force"
if errorlevel 1 (
  echo Extract failed.
  pause
  exit /b 1
)

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
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'DeskTrack Agent.lnk')); $s.TargetPath = 'python'; $s.Arguments = '\"%INSTALL_DIR%\desktrack_agent.py\"'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Save()"

echo.
echo Done.
echo  1. Open https://desktrack.hairscalptradingco.com in Chrome
echo  2. Log in - My desk - click Enroll face (allow camera)
echo  3. Then start DeskTrack Agent from your Desktop
echo.
pause

cd /d "%INSTALL_DIR%"
python desktrack_agent.py
