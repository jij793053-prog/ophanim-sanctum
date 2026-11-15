@echo off
setlocal
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0ophanim_app_launcher.pyw"
    exit /b 0
)
where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw "%~dp0ophanim_app_launcher.pyw"
    exit /b 0
)
where python >nul 2>nul
if %errorlevel%==0 (
    start "" python "%~dp0ophanim_app_launcher.pyw"
    exit /b 0
)
echo [Ophanim Sanctum] Python 3.10+ not found in PATH. Opening standalone HTML preview...
start "" "%~dp0ophanim_sanctum.html"
