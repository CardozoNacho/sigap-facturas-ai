$ErrorActionPreference = 'Stop'
$directorioServicio = $PSScriptRoot
$directorioLogs = Join-Path $directorioServicio 'output\servicio'
New-Item -ItemType Directory -Path $directorioLogs -Force | Out-Null
$logServicio = Join-Path $directorioLogs ('inicio-automatico-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
try {
    Set-Location -LiteralPath $directorioServicio
    . (Join-Path $PSScriptRoot 'entorno_lector.ps1')
    $entornoServicio = Get-EntornoLector
    $pythonServicio = $entornoServicio.PythonExe
    # HTTPServer escribe accesos normales en stderr. Redirigir a archivos
    # nativos evita que Windows PowerShell los convierta en errores terminantes.
    $procesoServicio = Start-Process -FilePath $pythonServicio -ArgumentList @(
        ('"' + (Join-Path $directorioServicio 'servicio_lector.py') + '"'),
        '--host', $entornoServicio.HostEscucha, '--puerto', [string]$entornoServicio.Puerto,
        '--permitir', $entornoServicio.EquiposPermitidos
    ) -WorkingDirectory $directorioServicio -WindowStyle Hidden -RedirectStandardOutput $logServicio -RedirectStandardError ($logServicio + '.stderr.log') -Wait -PassThru
    exit $procesoServicio.ExitCode
} catch {
    $_ | Out-String | Add-Content -LiteralPath $logServicio
    exit 1
}
