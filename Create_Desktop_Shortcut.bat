@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root = $env:ROOT; $ws = New-Object -ComObject WScript.Shell; $desk = [Environment]::GetFolderPath('Desktop'); $s = $ws.CreateShortcut((Join-Path $desk 'Ophanim Sanctum.lnk')); $pyw = $null; foreach ($c in @(Get-Command pythonw -All -ErrorAction SilentlyContinue)) { if ($c.Source -and ($c.Source -notlike '*\WindowsApps\*') -and (Test-Path -LiteralPath $c.Source)) { try { $p = Start-Process -FilePath $c.Source -ArgumentList @('-c', 'pass') -Wait -PassThru -WindowStyle Hidden -ErrorAction Stop; if ($p.ExitCode -eq 0) { $pyw = $c.Source; break } } catch {} } }; if (-not $pyw) { $s.TargetPath = Join-Path $root 'Start_Ophanim_Sanctum.bat'; $s.Arguments = '' } else { $q = [char]34; $s.TargetPath = $pyw; $s.Arguments = $q + (Join-Path $root 'ophanim_app_launcher.pyw') + $q }; $s.WorkingDirectory = $root; $s.IconLocation = (Join-Path $root 'ophanim_logo.ico') + ',0'; $s.WindowStyle = 7; $s.Description = 'Ophanim Sanctum 3D Astrolabe'; $s.Save()"
echo [OK] 已在桌面生成带圣轮玫瑰星盘 LOGO 的快捷方式：Ophanim Sanctum
pause
