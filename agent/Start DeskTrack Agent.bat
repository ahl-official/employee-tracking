@echo off
cd /d "%~dp0"
if not exist config.ini (
  echo Copy config.example.ini to config.ini and fill your login first.
  pause
  exit /b 1
)
python desktrack_agent.py
pause
