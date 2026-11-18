param([int]$Puerto = 0, [string]$HostEscucha = '')
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
. (Join-Path $PSScriptRoot 'entorno_lector.ps1')
$entornoServicio = Get-EntornoLector
if (-not $Puerto) { $Puerto = $entornoServicio.Puerto }
if (-not $HostEscucha) { $HostEscucha = $entornoServicio.HostEscucha }
# Windows PowerShell no debe tratar los accesos HTTP de stderr como errores.
$ErrorActionPreference = 'Continue'
& $entornoServicio.PythonExe (Join-Path $PSScriptRoot 'servicio_lector.py') --host $HostEscucha --puerto $Puerto --permitir $entornoServicio.EquiposPermitidos
exit $LASTEXITCODE
