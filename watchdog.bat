@echo off
REM ============================================================
REM AGENTX Service Manager — HermesJatti Watchdog
REM Starts & maintains: Backend (port 8000), Bridge (port 5000)
REM ============================================================
cd /d "C:\Trading"

set LOGDIR=C:\Trading\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

:check_bridge
REM Check if bridge is running on port 5000
netstat -ano | findstr ":5000 " | findstr LISTENING >nul
if errorlevel 1 (
    echo [%date% %time%] Bridge DOWN — restarting...
    start /B "" python -m bridge > "%LOGDIR%\bridge.log" 2>&1
    echo [%date% %time%] Bridge started
) else (
    REM Already running — silently OK
)

:check_backend
REM Check if backend is running on port 8000
netstat -ano | findstr ":8000 " | findstr LISTENING >nul
if errorlevel 1 (
    echo [%date% %time%] Backend DOWN — restarting...
    start /B "" python -m backend --host 0.0.0.0 > "%LOGDIR%\backend.log" 2>&1
    echo [%date% %time%] Backend started
) else (
    REM Already running — silently OK
)

REM Wait 60 seconds then loop
timeout /t 60 /nobreak >nul
goto check_bridge
