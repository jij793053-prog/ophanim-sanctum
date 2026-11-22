@echo off
setlocal
cd /d "%~dp0"

set "PY_BIN="
set "PY_ARGS="

for /f "delims=" %%P in ('where pythonw 2^>nul') do if not defined PY_BIN call :probe_py "%%~fP" ""
if not defined PY_BIN for /f "delims=" %%P in ('where pyw 2^>nul') do if not defined PY_BIN call :probe_py "%%~fP" "-3"
if not defined PY_BIN for /f "delims=" %%P in ('where python 2^>nul') do if not defined PY_BIN call :probe_py "%%~fP" ""

if defined PY_BIN (
    if defined PY_ARGS (
        start "" "%PY_BIN%" %PY_ARGS% "%~dp0ophanim_app_launcher.pyw"
    ) else (
        start "" "%PY_BIN%" "%~dp0ophanim_app_launcher.pyw"
    )
    exit /b 0
)

echo [Ophanim Sanctum] Python 3.10+ not found in PATH ^(WindowsApps stubs ignored^). Opening standalone HTML preview...
start "" "%~dp0ophanim_sanctum.html"
exit /b 0

:probe_py
set "CAND=%~1"
set "CARG=%~2"
if not exist "%CAND%" exit /b 1
if /i not "%CAND:\WindowsApps\=%"=="%CAND%" exit /b 1
if "%CARG%"=="" (
    "%CAND%" -c "import sys" >nul 2>nul
) else (
    "%CAND%" %CARG% -c "import sys" >nul 2>nul
)
if errorlevel 1 exit /b 1
set "PY_BIN=%CAND%"
set "PY_ARGS=%CARG%"
exit /b 0
