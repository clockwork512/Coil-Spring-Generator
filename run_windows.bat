@echo off
rem Runs the app from source using the .venv created by build_windows.bat
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
    echo Run build_windows.bat first to set up Python packages.
    pause
    exit /b 1
)
start "" .venv\Scripts\pythonw.exe run.py
