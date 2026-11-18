param(
    [Parameter(Mandatory=$true)][string]$CarpetaTomcat,
    [string]$Destino = ''
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $CarpetaTomcat -PathType Container)) { throw 'No existe la carpeta Tomcat indicada.' }
if (-not $Destino) { $Destino = Join-Path ([Environment]::GetFolderPath('MyDocuments')) ('SigapDiagnostico-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
New-Item -ItemType Directory -Path $Destino -Force | Out-Null
# Solo lectura y consultas: no reinicia Tomcat ni modifica su configuracion.
Get-Date -Format o | Set-Content -LiteralPath (Join-Path $Destino 'hora.txt')
$directorioLogs = Join-Path $CarpetaTomcat 'logs'
if (Test-Path -LiteralPath $directorioLogs) {
    $archivosLogs = Get-ChildItem -LiteralPath $directorioLogs -File |
        Where-Object { $_.Name -match '^(catalina|localhost)' -and $_.Extension -in @('.log','.txt') } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 6
    foreach ($archivoLog in $archivosLogs) {
        Get-Content -LiteralPath $archivoLog.FullName -Tail 5000 |
            Select-String -Pattern 'lector IA|FacturaIA|transferencia|SocketException|SocketTimeoutException|IOException|OutOfMemoryError|ClientAbortException' -Context 2,5 |
            Out-String -Width 300 | Set-Content -LiteralPath (Join-Path $Destino ($archivoLog.Name + '.filtrado.txt'))
    }
}
$procesosTomcat = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '^javaw?\.exe$' -and $_.CommandLine -match 'org\.apache\.catalina\.startup\.Bootstrap'
})
foreach ($procesoTomcat in $procesosTomcat) {
    if (-not $procesoTomcat.ExecutablePath) { continue }
    $jcmdTomcat = Join-Path (Split-Path $procesoTomcat.ExecutablePath -Parent) 'jcmd.exe'
    if (Test-Path -LiteralPath $jcmdTomcat) {
        $registroHilos = Join-Path $Destino ('hilos-' + $procesoTomcat.ProcessId + '.txt')
        $registroErrores = Join-Path $Destino ('hilos-' + $procesoTomcat.ProcessId + '.error.txt')
        $capturaTomcat = Start-Process -FilePath $jcmdTomcat -ArgumentList @([string]$procesoTomcat.ProcessId,'Thread.print','-l') -WindowStyle Hidden -PassThru -RedirectStandardOutput $registroHilos -RedirectStandardError $registroErrores
        if (-not $capturaTomcat.WaitForExit(15000)) { Write-Warning 'La captura de hilos sigue esperando. Tomcat no se detuvo.' }
    }
}
netstat -ano -p tcp | Select-String ':8765' | Out-String | Set-Content -LiteralPath (Join-Path $Destino 'conexiones-lector.txt')
Write-Host ('Diagnostico guardado en: ' + $Destino)
Write-Host 'Tomcat no se reinicio ni se modifico. Los archivos filtrados pueden estar vacios si el error aun no se registro.'
