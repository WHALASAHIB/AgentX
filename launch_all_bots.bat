@echo off
REM ============================================================
REM LAUNCH ALL ACTIVE BOTS — Percentage-based sizing v2
REM Starts only symbols with risk > 0.0 in DEFAULT_PARAMS
REM ============================================================
cd /d C:\Trading
set PYTHON=C:\Users\nryur\AppData\Local\Programs\Python\Python312\python.exe
set BOTS_DIR=C:\Trading\bots\active_bots
set LOG_DIR=C:\Trading\bots\logs

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo [%date% %time%] Launching all active bots... >> %LOG_DIR%\launcher.log

REM AUDUSD
start "AUDUSD-MACD" /MIN "%PYTHON%" "%BOTS_DIR%\AUDUSD\run_macd.py"
start "AUDUSD-BOLLINGER" /MIN "%PYTHON%" "%BOTS_DIR%\AUDUSD\run_bollinger.py"

REM BTCUSD
start "BTCUSD-MACD" /MIN "%PYTHON%" "%BOTS_DIR%\BTCUSD\run_macd.py"
start "BTCUSD-GOLDPHOENIX" /MIN "%PYTHON%" "%BOTS_DIR%\BTCUSD\run_goldphoenix.py"
start "BTCUSD-SMA" /MIN "%PYTHON%" "%BOTS_DIR%\BTCUSD\run_sma.py"

REM GBPUSD
start "GBPUSD-MACD" /MIN "%PYTHON%" "%BOTS_DIR%\GBPUSD\run_macd.py"
start "GBPUSD-GOLDPHOENIX" /MIN "%PYTHON%" "%BOTS_DIR%\GBPUSD\run_goldphoenix.py"

REM NZDUSD
start "NZDUSD-MACD" /MIN "%PYTHON%" "%BOTS_DIR%\NZDUSD\run_macd.py"
start "NZDUSD-BOLLINGER" /MIN "%PYTHON%" "%BOTS_DIR%\NZDUSD\run_bollinger.py"

REM USDCAD
start "USDCAD-MACD" /MIN "%PYTHON%" "%BOTS_DIR%\USDCAD\run_macd.py"
start "USDCAD-GOLDPHOENIX" /MIN "%PYTHON%" "%BOTS_DIR%\USDCAD\run_goldphoenix.py"

REM USDCHF
start "USDCHF-MACD" /MIN "%PYTHON%" "%BOTS_DIR%\USDCHF\run_macd.py"
start "USDCHF-BOLLINGER" /MIN "%PYTHON%" "%BOTS_DIR%\USDCHF\run_bollinger.py"

REM USDJPY
start "USDJPY-MACD" /MIN "%PYTHON%" "%BOTS_DIR%\USDJPY\run_macd.py"
start "USDJPY-SMA" /MIN "%PYTHON%" "%BOTS_DIR%\USDJPY\run_sma.py"

echo [%date% %time%] All 15 active bots launched. >> %LOG_DIR%\launcher.log
echo Active bots launched.
