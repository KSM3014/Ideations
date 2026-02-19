@echo off
setlocal enabledelayedexpansion

set "PYTHON=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
set "PROJECT=C:\Users\Administrator\Desktop\Projects\IDEATIONs\idea generator"
set "PATH=C:\Users\Administrator\AppData\Local\Programs\Python\Python311;C:\Users\Administrator\AppData\Roaming\npm;%PATH%"

cd /d "%PROJECT%"

if not exist "%PROJECT%\output\logs" mkdir "%PROJECT%\output\logs"

for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /format:list') do set "dt=%%a"
set "LOGFILE=%PROJECT%\output\logs\engine_%dt:~0,8%_%dt:~8,4%.log"

if not exist "%PYTHON%" (
    echo [FATAL] Python not found >> "%LOGFILE%" 2>&1
    exit /b 1
)

echo [%date% %time%] Engine starting >> "%LOGFILE%" 2>&1
"%PYTHON%" "%PROJECT%\scripts\run_engine.py" %* >> "%LOGFILE%" 2>&1
set "EXIT_CODE=%errorlevel%"
echo [%date% %time%] Exit code: %EXIT_CODE% >> "%LOGFILE%" 2>&1

endlocal
exit /b %EXIT_CODE%
