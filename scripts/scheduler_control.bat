@echo off
REM API Ideation Engine v6.0 — Windows 작업 스케줄러 제어
REM 사용법:
REM   scheduler_control.bat install   — 매시 정각 작업 등록
REM   scheduler_control.bat remove    — 작업 제거
REM   scheduler_control.bat status    — 작업 상태 확인
REM   scheduler_control.bat run-now   — 즉시 1회 실행

setlocal enabledelayedexpansion

set "TASK_NAME=APIIdeationEngine_v6"
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "ENGINE_BAT=%SCRIPT_DIR%run_engine.bat"

if "%~1"=="" goto :usage

if /i "%~1"=="install" goto :install
if /i "%~1"=="remove" goto :remove
if /i "%~1"=="status" goto :status
if /i "%~1"=="run-now" goto :runnow
goto :usage

:install
echo Installing scheduled task: %TASK_NAME%
echo   Schedule: Every hour at :00
echo   Script: %ENGINE_BAT%
schtasks /create /tn "%TASK_NAME%" ^
    /tr "\"%ENGINE_BAT%\"" ^
    /sc HOURLY ^
    /mo 1 ^
    /st 00:00 ^
    /ru "%USERNAME%" ^
    /rl HIGHEST ^
    /f
if %errorlevel% equ 0 (
    echo Task installed successfully.
) else (
    echo Failed to install task. Run as Administrator.
)
goto :eof

:remove
echo Removing scheduled task: %TASK_NAME%
schtasks /delete /tn "%TASK_NAME%" /f
if %errorlevel% equ 0 (
    echo Task removed successfully.
) else (
    echo Failed to remove task.
)
goto :eof

:status
echo Checking task status: %TASK_NAME%
schtasks /query /tn "%TASK_NAME%" /v /fo LIST 2>nul
if %errorlevel% neq 0 (
    echo Task not found. Use 'scheduler_control.bat install' to create it.
)
goto :eof

:runnow
echo Running engine once (immediate)...
call "%ENGINE_BAT%"
goto :eof

:usage
echo Usage: scheduler_control.bat [install^|remove^|status^|run-now]
echo.
echo   install   Register hourly task in Windows Task Scheduler
echo   remove    Remove the scheduled task
echo   status    Show current task status
echo   run-now   Run the engine immediately (once)
goto :eof
