$ErrorActionPreference = 'Stop'
$nombreTarea = 'SIGAP Lector de facturas'
$usuarioServicio = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$scriptServicio = Join-Path $PSScriptRoot 'iniciar_servicio_automatico.ps1'
. (Join-Path $PSScriptRoot 'entorno_lector.ps1')
$entornoServicio = Get-EntornoLector
if (Get-ScheduledTask -TaskName $nombreTarea -ErrorAction SilentlyContinue) {
    throw 'La tarea ya existe. Revisar su configuracion antes de reemplazarla.'
}
$accionServicio = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $scriptServicio + '"') -WorkingDirectory $PSScriptRoot
$disparadorServicio = New-ScheduledTaskTrigger -AtStartup
$disparadorServicio.Delay = 'PT30S'
$cuentaServicio = New-ScheduledTaskPrincipal -UserId $usuarioServicio -LogonType S4U -RunLevel Limited
$opcionesServicio = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $nombreTarea -Action $accionServicio -Trigger $disparadorServicio -Principal $cuentaServicio -Settings $opcionesServicio -Description 'Servidor HTTP local de extraccion de facturas SIGAP. Arranca con Windows sin iniciar sesion; usa archivos locales y recibe solicitudes de SIGAP.' | Select-Object TaskName,State
