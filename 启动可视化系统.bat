@echo off
title Xiongan Traffic Visualization Server
echo ========================================
echo   Xiongan Traffic Visualization Server
echo ========================================
echo.

REM Check SUMO_HOME
if "%SUMO_HOME%"=="" (
    echo [ERROR] SUMO_HOME is not set.
    echo Please set SUMO_HOME first, e.g.:
    echo   set SUMO_HOME=C:\Program Files (x86)\Eclipse\Sumo
    pause
    exit /b 1
)

echo SUMO_HOME = %SUMO_HOME%
echo.

REM Select scenario
echo Select initial scenario:
echo   1. morning  (recommended)
echo   2. evening
echo   3. flat
echo   4. no model (fixed timing)
set /p choice="Enter choice (1-4, default 1): "

set SCENARIO=morning
set MODEL_FLAG=

if "%choice%"=="2" set SCENARIO=evening
if "%choice%"=="3" set SCENARIO=flat
if "%choice%"=="4" set MODEL_FLAG=--no-model

echo.
echo Starting... scenario=%SCENARIO% %MODEL_FLAG%
echo.

cd /d "%~dp0.."
python server/visualization_server.py --scenario %SCENARIO% %MODEL_FLAG% --port 8765

echo.
echo Server stopped.
pause
