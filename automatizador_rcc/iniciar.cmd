@echo off
setlocal
set "rcc_programa=%~dp0"
if not exist "%rcc_programa%.venv\Scripts\python.exe" set "rcc_programa=%LOCALAPPDATA%\SIGAP\RCC\programa\"
if not exist "%rcc_programa%.venv\Scripts\python.exe" goto no_instalado
if not exist "%rcc_programa%rcc_bridge.py" goto no_instalado
"%rcc_programa%.venv\Scripts\python.exe" "%rcc_programa%rcc_bridge.py"
set "rcc_exit=%errorlevel%"
if errorlevel 1 echo No se pudo iniciar. Configure SIGAP RCC y compruebe que no haya otra instancia.
pause
exit /b %rcc_exit%

:no_instalado
echo SIGAP RCC no esta instalado o su instalacion esta incompleta.
echo Ejecute instalar.cmd desde el paquete descargado.
pause
exit /b 1
