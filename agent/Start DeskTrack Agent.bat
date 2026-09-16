@echo off
REM Starts agent hidden (no terminal). Prefer this after install.
set "DIR=%~dp0"
if exist "%DIR%Start-Hidden.vbs" (
  wscript //nologo "%DIR%Start-Hidden.vbs"
) else (
  start "" /B pythonw "%DIR%desktrack_agent.py"
)
