@echo off
setlocal enabledelayedexpansion

rem ===== ABSOLUTE PATHS (ASCII only, no Korean) =====
set "PYTHON=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
set "PROJECT=C:\Users\Administrator\Desktop\Projects\IDEATIONs\idea generator"
set "CURL=C:\Windows\System32\curl.exe"
set "PATH=C:\Users\Administrator\AppData\Local\Programs\Python\Python311;C:\Users\Administrator\AppData\Roaming\npm;%PATH%"

cd /d "%PROJECT%"

rem ===== ENSURE LOG DIR =====
if not exist "%PROJECT%\output\logs" mkdir "%PROJECT%\output\logs"

rem ===== TIMESTAMP FOR LOG FILENAME =====
for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /format:list') do set "dt=%%a"
set "LOGFILE=%PROJECT%\output\logs\engine_%dt:~0,8%_%dt:~8,4%.log"

rem ===== LAYER 3-A: ENVIRONMENT PRE-CHECKS =====
set "PREFLIGHT_FAIL=0"

if not exist "%PYTHON%" (
    echo [FATAL] Python not found: %PYTHON% >> "%LOGFILE%" 2>&1
    set "PREFLIGHT_FAIL=1"
    set "FAIL_REASON=Python not found at %PYTHON%"
)

if not exist "%PROJECT%\data\public_api_catalog.sqlite3" (
    echo [FATAL] Catalog DB not found >> "%LOGFILE%" 2>&1
    set "PREFLIGHT_FAIL=1"
    set "FAIL_REASON=Catalog DB not found"
)

if not exist "%PROJECT%\scripts\run_engine.py" (
    echo [FATAL] run_engine.py not found >> "%LOGFILE%" 2>&1
    set "PREFLIGHT_FAIL=1"
    set "FAIL_REASON=run_engine.py not found"
)

rem ===== LAYER 3-B: IF PREFLIGHT FAILED, ALERT AND EXIT =====
if "%PREFLIGHT_FAIL%"=="1" (
    echo [%date% %time%] PREFLIGHT FAILED: !FAIL_REASON! >> "%LOGFILE%" 2>&1
    call :SEND_ALERT "Scheduler preflight FAILED: !FAIL_REASON!"
    endlocal
    exit /b 99
)

rem ===== RUN ENGINE =====
echo [%date% %time%] Engine starting >> "%LOGFILE%" 2>&1
"%PYTHON%" "%PROJECT%\scripts\run_engine.py" %* >> "%LOGFILE%" 2>&1
set "EXIT_CODE=%errorlevel%"
echo [%date% %time%] Exit code: %EXIT_CODE% >> "%LOGFILE%" 2>&1

rem ===== LAYER 3-C: IF ENGINE FAILED, ALERT =====
if not "%EXIT_CODE%"=="0" (
    echo [%date% %time%] ENGINE FAILED, sending alert >> "%LOGFILE%" 2>&1
    call :SEND_ALERT "Engine exited with code %EXIT_CODE%. Check log: %LOGFILE%"
)

endlocal
exit /b %EXIT_CODE%

rem ===== DISCORD ALERT SUBROUTINE =====
:SEND_ALERT
set "MSG=%~1"
set "WEBHOOK_CFG=%PROJECT%\data\webhook_config.json"

if not exist "%WEBHOOK_CFG%" (
    echo [WARN] No webhook config, cannot send alert >> "%LOGFILE%" 2>&1
    goto :EOF
)

rem Extract webhook URL from JSON using Python one-liner
for /f "usebackq delims=" %%u in (`"%PYTHON%" -c "import json; print(json.load(open(r'%WEBHOOK_CFG%'))['discord_webhook_url'])" 2^>nul`) do set "WEBHOOK_URL=%%u"

if not defined WEBHOOK_URL (
    echo [WARN] Could not extract webhook URL >> "%LOGFILE%" 2>&1
    goto :EOF
)

rem Send alert via curl
"%CURL%" -s -H "Content-Type: application/json" -d "{\"embeds\":[{\"title\":\"\\u26a0\\ufe0f Scheduler Alert\",\"description\":\"%MSG%\",\"color\":16729600}]}" "%WEBHOOK_URL%" >> "%LOGFILE%" 2>&1
echo [%date% %time%] Discord alert sent >> "%LOGFILE%" 2>&1
goto :EOF
