@echo off
rem HR-System DEMO with realistic synthetic data (a separate installation; never touches real data).
rem Start-HR-Demo.bat -Reset   rebuilds the demo from scratch.
rem Start-HR-Demo.bat -NoBrowser (or --background) starts without opening Chrome.
cd /d "%~dp0"
set "demoArgs=%*"
set "demoArgs=%demoArgs:--background=-NoBrowser%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_demo.ps1" %demoArgs%
if errorlevel 1 pause
