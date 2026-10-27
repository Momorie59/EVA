@echo off
chcp 65001 >nul
title Desinstallation du satellite EVA
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Droits administrateur necessaires : Windows va demander l'autorisation...
  >"%PUBLIC%\eva-profil.txt" echo %USERPROFILE%
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
set "EVA_PROFIL=%USERPROFILE%"
if exist "%PUBLIC%\eva-profil.txt" set /p EVA_PROFIL=<"%PUBLIC%\eva-profil.txt"
del "%PUBLIC%\eva-profil.txt" 2>nul
echo Desinstallation du satellite EVA de cet ordinateur...
schtasks /End /TN "EVA Satellite" >nul 2>&1
schtasks /Delete /TN "EVA Satellite" /F >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter 'Name like ''python%%'' '  | Where-Object { $_.CommandLine -like '*eva-satellite*' -or $_.ExecutablePath -like '*eva-satellite*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
del "%EVA_PROFIL%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\eva-satellite.cmd" 2>nul
del "%EVA_PROFIL%\Desktop\EVA pause.cmd" "%EVA_PROFIL%\Desktop\EVA reprise.cmd" "%EVA_PROFIL%\Desktop\EVA d*marrer.cmd" "%EVA_PROFIL%\Desktop\EVA arr*ter.cmd" 2>nul
timeout /t 2 /nobreak >nul
cd /d "%EVA_PROFIL%"
echo.
echo Le satellite est desinstalle. Pense a le supprimer aussi dans EVA (Maison - Satellites) s il y est encore.
pause
rmdir /s /q "%EVA_PROFIL%\eva-satellite" 2>nul & exit /b
