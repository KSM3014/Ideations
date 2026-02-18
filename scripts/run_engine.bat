@echo off
REM API Ideation Engine v6.0 — Windows 실행 래퍼
REM 작업 스케줄러에서 매시 정각 호출용
REM 사용법: run_engine.bat [--manual-signals "텍스트"]

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
cd /d "%PROJECT_ROOT%"

REM Python 가상환경 활성화 (있는 경우)
if exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
)

REM output 디렉토리 보장
if not exist "%PROJECT_ROOT%\output\signals" mkdir "%PROJECT_ROOT%\output\signals"
if not exist "%PROJECT_ROOT%\output\hypotheses" mkdir "%PROJECT_ROOT%\output\hypotheses"
if not exist "%PROJECT_ROOT%\output\validations" mkdir "%PROJECT_ROOT%\output\validations"
if not exist "%PROJECT_ROOT%\output\reports" mkdir "%PROJECT_ROOT%\output\reports"
if not exist "%PROJECT_ROOT%\output\logs" mkdir "%PROJECT_ROOT%\output\logs"

REM 엔진 실행
echo [%date% %time%] Starting API Ideation Engine v6.0...
python "%SCRIPT_DIR%run_engine.py" %*

set "EXIT_CODE=%errorlevel%"
if %EXIT_CODE% neq 0 (
    echo [%date% %time%] Engine exited with code %EXIT_CODE%
) else (
    echo [%date% %time%] Engine completed successfully
)

endlocal
exit /b %EXIT_CODE%
