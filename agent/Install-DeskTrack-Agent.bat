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
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS=%INSTALL_DIR%\Start-Hidden.vbs"

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
set "SERVER=https://desktrack.hairscalptradingco.com"
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

REM Prefer pythonw so no console stays open
set "PYW="
for /f "delims=" %%I in ('where pythonw 2^>nul') do (
  if not defined PYW set "PYW=%%I"
)
if not defined PYW set "PYW=pythonw"
where pythonw >nul 2>&1
if errorlevel 1 set "PYW=python"

echo Creating silent starter...
(
  echo Set sh = CreateObject^("WScript.Shell"^)
  echo sh.CurrentDirectory = "%INSTALL_DIR%"
  echo sh.Run """%PYW%"" ""%INSTALL_DIR%\desktrack_agent.py""", 0, False
) > "%VBS%"

echo Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'DeskTrack Agent.lnk')); $s.TargetPath = '%VBS%'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.WindowStyle = 7; $s.Save()"

echo Adding Windows Startup entry (runs every login, no daily click)...
if not exist "%STARTUP%" mkdir "%STARTUP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTUP%\DeskTrack Agent.lnk'); $s.TargetPath = '%VBS%'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.WindowStyle = 7; $s.Save()"

echo.
echo Starting agent in the background (no terminal window)...
wscript //nologo "%VBS%"

echo.
echo Done. Install finished — this window can close.
echo  - Agent is running hidden now
echo  - It will start again when you sign in to Windows
echo  - Enroll your face once on the website: My desk
echo  - You do NOT need to run this installer every day
echo.
pause
exit /b 0
