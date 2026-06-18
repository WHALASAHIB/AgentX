@echo off
set PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
if not exist "%PY%" (
    echo Python 3.12 not found at %PY%
    pause
    exit /b 1
)
echo Checking MetaTrader 5 connection...
echo.
cd /d "%~dp0\.."
"%PY%" utils\test_mt5.py
if errorlevel 1 "%PY%" utils\diagnose_mt5.py
pause
