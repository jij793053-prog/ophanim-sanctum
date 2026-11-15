@echo off
setlocal
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0ophanim_toy_launcher.pyw"
    exit /b 0
)
where python >nul 2>nul
if %errorlevel%==0 (
    start "" python "%~dp0ophanim_toy_launcher.pyw"
    exit /b 0
)
start "" "%~dp0ophanim_toy_sanctum.html"
