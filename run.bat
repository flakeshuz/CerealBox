@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    set "PYTHON=python"
) else (
    set "PYTHON=py -3"
)

%PYTHON% -c "import sys; raise SystemExit(sys.version_info < (3, 11))"
if errorlevel 1 (
    echo Python 3.11 or newer is required but was not found.
    exit /b 1
)

%PYTHON% -c "import cryptography, PyQt6" >nul 2>nul
if errorlevel 1 (
    echo Installing CerealBox dependencies...
    %PYTHON% -m pip install --user --disable-pip-version-check .
    if errorlevel 1 exit /b %errorlevel%
)

%PYTHON% main.py %*
exit /b %errorlevel%
