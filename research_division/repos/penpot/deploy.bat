@echo off
REM =====================================================
REM Penpot Deployment Script for Windows
REM Software Engineering (UI/UX) Department
REM =====================================================
setlocal enabledelayedexpansion

set "PENPOT_DIR=C:\Trading\research_division\repos\penpot"
set "COMPOSE_DIR=%PENPOT_DIR%\docker\images"

echo ========================================
echo    Penpot Deployment Tool - Windows
echo ========================================
echo.

:menu
echo Choose an action:
echo [1] Deploy (start all services)
echo [2] Stop all services
echo [3] Restart all services
echo [4] View status
echo [5] View logs
echo [6] Update Penpot
echo [7] Full teardown (removes ALL data)
echo [8] Check prerequisites
echo [9] Exit
echo.
set /p choice="Enter choice (1-9): "

if "%choice%"=="1" goto deploy
if "%choice%"=="2" goto stop
if "%choice%"=="3" goto restart
if "%choice%"=="4" goto status
if "%choice%"=="5" goto logs
if "%choice%"=="6" goto update
if "%choice%"=="7" goto teardown
if "%choice%"=="8" goto prereq
if "%choice%"=="9" goto end
echo Invalid choice. Please try again.
echo.
goto menu

:prereq
echo.
echo Checking prerequisites...
echo.
where docker >nul 2>&1
if %errorlevel% neq 0 (
    echo [FAIL] Docker is NOT installed.
    echo.
    echo Please install Docker Desktop from:
    echo https://www.docker.com/products/docker-desktop/
    echo.
    echo After installing, restart this script.
    goto end
) else (
    echo [OK] Docker is installed.
    for /f "tokens=*" %%i in ('docker --version') do echo       Version: %%i
)
echo.
docker compose version >nul 2>&1
if %errorlevel% neq 0 (
    echo [FAIL] Docker Compose is NOT available.
    goto end
) else (
    echo [OK] Docker Compose is available.
    for /f "tokens=*" %%i in ('docker compose version') do echo       Version: %%i
)
echo.
echo [INFO] Checking Docker Desktop is running...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Docker Desktop may not be running.
    echo        Please start Docker Desktop from the system tray.
) else (
    echo [OK] Docker Desktop is running.
)
echo.
goto end

:deploy
echo.
echo Deploying Penpot...
cd /d "%COMPOSE_DIR%"
if %errorlevel% neq 0 (
    echo [ERROR] Could not find directory: %COMPOSE_DIR%
    goto end
)
docker compose up -d
if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] Penpot is deploying!
    echo.
    echo Access Penpot at: http://localhost:9001
    echo MailCatcher UI:   http://localhost:1080
    echo.
    echo Run 'docker compose ps' to check status.
) else (
    echo [ERROR] Deployment failed.
)
goto end

:stop
echo.
echo Stopping Penpot services...
cd /d "%COMPOSE_DIR%"
docker compose down
if %errorlevel% equ 0 (
    echo [SUCCESS] Penpot services stopped.
) else (
    echo [ERROR] Failed to stop services.
)
goto end

:restart
echo.
echo Restarting Penpot services...
cd /d "%COMPOSE_DIR%"
docker compose restart
if %errorlevel% equ 0 (
    echo [SUCCESS] Penpot services restarted.
) else (
    echo [ERROR] Failed to restart services.
)
goto end

:status
echo.
echo Penpot service status:
cd /d "%COMPOSE_DIR%"
docker compose ps
goto end

:logs
echo.
echo Showing logs (press Ctrl+C to exit)...
cd /d "%COMPOSE_DIR%"
docker compose logs -f
goto end

:update
echo.
echo Updating Penpot to latest version...
cd /d "%COMPOSE_DIR%"
echo [INFO] Pulling latest images...
docker compose pull
if %errorlevel% equ 0 (
    echo [INFO] Recreating containers...
    docker compose up -d
    echo [SUCCESS] Penpot updated!
) else (
    echo [ERROR] Update failed.
)
goto end

:teardown
echo.
echo WARNING: This will remove ALL containers and ALL data (database, assets).
echo This action CANNOT be undone.
echo.
set /p confirm="Are you sure you want to proceed? (yes/no): "
if /i "!confirm!"=="yes" (
    cd /d "%COMPOSE_DIR%"
    docker compose down -v
    echo [INFO] Teardown complete.
) else (
    echo [INFO] Teardown cancelled.
)
goto end

:end
echo.
echo Press any key to exit...
pause >nul
endlocal
