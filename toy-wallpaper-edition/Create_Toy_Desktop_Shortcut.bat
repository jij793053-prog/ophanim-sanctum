@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $desk = [Environment]::GetFolderPath('Desktop'); $s = $ws.CreateShortcut((Join-Path $desk 'Ophanim Toy Sanctum.lnk')); $pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source; if (-not $pyw) { $pyw = Join-Path '%ROOT%' 'Start_Toy_Wallpaper_App.bat' } else { $s.Arguments = '"' + (Join-Path '%ROOT%' 'ophanim_toy_launcher.pyw') + '"' }; $s.TargetPath = $pyw; $s.WorkingDirectory = '%ROOT%'; $s.IconLocation = (Join-Path '%ROOT%' 'ophanim_logo.ico') + ',0'; $s.WindowStyle = 7; $s.Description = 'Ophanim Toy Sanctum & Interactive Wallpaper'; $s.Save()"
echo [OK] 已在桌面生成带圣轮玫瑰星盘 LOGO 的快捷方式：Ophanim Toy Sanctum
pause
