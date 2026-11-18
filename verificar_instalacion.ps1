$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'entorno_lector.ps1')
$entornoVerificacion = Get-EntornoLector
& $entornoVerificacion.PythonExe -c "import sys; from importlib.metadata import version; import pdf2image, PIL, pypdf; print('Python:', sys.version.split()[0]); print('\n'.join(n+'=='+version(n) for n in ['pdf2image','Pillow','pypdf']))"
if ($LASTEXITCODE -ne 0) { throw 'Faltan dependencias Python.' }
Write-Host ('Poppler: '+(Get-Command pdfinfo.exe).Source)
$modelosVerificacion = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 10
if (-not (@($modelosVerificacion.models | Where-Object { $_.name -eq 'qwen3-vl:2b-instruct' }).Count)) {
    throw 'Ollama responde pero no tiene qwen3-vl:2b-instruct. Descargar/importar el modelo.'
}
Write-Host 'Ollama responde y el modelo esta registrado. No se ejecuto inferencia.'
$claveVerificacion = Join-Path $PSScriptRoot 'output\servicio\clave_api.txt'
if (Test-Path -LiteralPath $claveVerificacion) {
    $tokenVerificacion = (Get-Content -Raw -LiteralPath $claveVerificacion).Trim()
    $hostVerificacion = if ($entornoVerificacion.HostEscucha -eq '0.0.0.0') { '127.0.0.1' } else { $entornoVerificacion.HostEscucha }
    $saludVerificacion = Invoke-RestMethod -Uri ('http://'+$hostVerificacion+':'+$entornoVerificacion.Puerto+'/salud') -Headers @{Authorization=('Bearer '+$tokenVerificacion)} -TimeoutSec 10
    Write-Host ('Servicio lector: '+$saludVerificacion.estado)
} else {
    Write-Host 'Servicio lector sin inicializar. Iniciarlo para generar su clave y verificar HTTP.'
}
