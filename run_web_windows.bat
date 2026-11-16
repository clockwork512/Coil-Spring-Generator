@echo off
setlocal
cd /d "%~dp0"
title Coil Spring Designer - website

rem ---- Python environment: reuse the one build_windows.bat made, or make it ----
if exist .venv\Scripts\python.exe goto :haveenv

echo.
echo  First run: setting up Python (this takes a few minutes, once)...
set "PY="
for %%V in (3.12 3.13 3.11 3.10) do if not defined PY call :try py -%%V
if not defined PY call :try py
if not defined PY call :try python
if not defined PY goto :nopython
%PY% -m venv .venv || goto :fail
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail

:haveenv
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo  Installing the web server packages...
    "%VPY%" -m pip install "fastapi>=0.110" "uvicorn>=0.29" || goto :fail
)

rem ---- start the site.  Add --local to keep it to this computer only. ----
"%VPY%" run_web.py %*
if errorlevel 1 goto :fail
exit /b 0


:try
%* -c "import sys,sysconfig; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) and sysconfig.get_platform()=='win-amd64' else 1)" >nul 2>&1
if not errorlevel 1 set "PY=%*"
exit /b 0

:nopython
echo.
echo   No compatible Python found. Install Python 3.12, "Windows installer (64-bit)":
echo     https://www.python.org/downloads/release/python-31210/
echo   then run this file again.
pause
exit /b 1

:fail
echo.
echo   The website stopped with an error - see the messages above.
echo   If it says the address is already in use, the site is probably
echo   already running in another window.
pause
exit /b 1
