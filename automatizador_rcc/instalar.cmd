@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
set "rcc_exit=%errorlevel%"
pause
exit /b %rcc_exit%
