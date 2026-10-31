@echo off
setlocal
cd /d "%~dp0"
title Coil Spring Designer - build

echo.
echo  Looking for a compatible Python (64-bit x64, version 3.10 - 3.13)...
set "PY="
for %%V in (3.12 3.13 3.11 3.10) do if not defined PY call :try py -%%V
if not defined PY call :try py
if not defined PY call :try python
if not defined PY goto :nopython

echo  Using: %PY%
%PY% -c "import sys; print('  Python', sys.version)"
echo.

if exist .venv (
    echo  Removing old .venv from previous attempt...
    rmdir /s /q .venv
)
%PY% -m venv .venv || goto :fail
set "VPY=.venv\Scripts\python.exe"

echo.
echo  Installing packages (CAD engine is a large download, be patient)...
"%VPY%" -m pip install --upgrade pip || goto :fail
"%VPY%" -m pip install -r requirements.txt pyinstaller || goto :fail

echo.
echo  Testing the CAD engine...
"%VPY%" run.py --selftest selftest.step || goto :fail
del selftest.step 2>nul

echo.
echo  Building the standalone app (takes several minutes)...
"%VPY%" -m PyInstaller --noconfirm CoilSpringDesigner.spec || goto :fail

echo.
echo  ==========================================================
echo   Build complete:
echo   dist\CoilSpringDesigner\CoilSpringDesigner.exe
echo  ==========================================================
start "" explorer "dist\CoilSpringDesigner"
pause
exit /b 0


:try
rem Accept this Python only if it is 3.10-3.13 and an x64 (win-amd64) build.
%* -c "import sys,sysconfig; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) and sysconfig.get_platform()=='win-amd64' else 1)" >nul 2>&1
if not errorlevel 1 set "PY=%*"
exit /b 0


:nopython
echo.
echo  ----------------------------------------------------------
echo   No compatible Python found.
echo.
echo   The CAD library only ships for 64-bit (x64) Python
echo   3.10, 3.11, 3.12 or 3.13 on Windows.
echo.
echo   Pythons on this PC:
py -0p 2>nul || python -c "import sys,sysconfig; print('  ', sys.version.split()[0], sysconfig.get_platform())" 2>nul
echo.
echo   Fix: install Python 3.12, "Windows installer (64-bit)":
echo     https://www.python.org/downloads/release/python-31210/
echo   It installs alongside any Python you already have.
echo   (On an ARM / Snapdragon PC, still pick the 64-bit x64
echo    installer, not ARM64 - it runs fine under emulation.)
echo   Then run this script again.
echo  ----------------------------------------------------------
pause
exit /b 1


:fail
echo.
echo  ----------------------------------------------------------
echo   Build FAILED - see the error messages above.
echo  ----------------------------------------------------------
pause
exit /b 1
