@echo off
rem HR-System PRESENTATION: opens on the set-up screen (as a new customer sees it), with a "Development stage: Skip" button that builds
rem the demo company with its data and goes straight in (sign in: admin / 123). A fresh empty installation every time; never touches real data.
rem Start-HR-Presentation.bat -NoBrowser starts without opening Chrome.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_presentation.ps1" %*
if errorlevel 1 pause
