@echo off
setlocal
set "rcc_programa=%~dp0"
if not exist "%rcc_programa%.venv\Scripts\python.exe" set "rcc_programa=%LOCALAPPDATA%\SIGAP\RCC\programa\"
if not exist "%rcc_programa%.venv\Scripts\python.exe" goto no_instalado
if not exist "%rcc_programa%configurar.py" goto no_instalado
"%rcc_programa%.venv\Scripts\python.exe" "%rcc_programa%configurar.py"
set "rcc_exit=%errorlevel%"
if "%rcc_exit%"=="0" exit /b 0
echo.
echo No se pudo abrir la configuracion. Revise el error indicado arriba.
pause
exit /b %rcc_exit%

:no_instalado
echo SIGAP RCC no esta instalado o su instalacion esta incompleta.
echo Ejecute instalar.cmd desde el paquete descargado y vuelva a abrir Configurar SIGAP RCC.
pause
exit /b 1
