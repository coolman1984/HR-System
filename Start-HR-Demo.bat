@echo off
rem HR-System DEMO with realistic synthetic data (a separate installation; never touches real data).
rem Start-HR-Demo.bat -Reset   rebuilds the demo from scratch.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_demo.ps1" %*
if errorlevel 1 pause
