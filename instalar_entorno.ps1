param(
    [Parameter(Mandatory=$true)][string]$PythonExe,
    [Parameter(Mandatory=$true)][string]$PopplerBin,
    [string]$EquiposPermitidos = '127.0.0.1',
    [string]$RepositorioPaquetes = ''
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath (Join-Path $PopplerBin 'pdfinfo.exe'))) { throw 'Indicar el directorio bin de Poppler que contiene pdfinfo.exe.' }
if (-not (Test-Path -LiteralPath (Join-Path $PopplerBin 'pdftoppm.exe'))) { throw 'Falta pdftoppm.exe en PopplerBin.' }
$destinoConfiguracion = Join-Path $PSScriptRoot 'configuracion\lector.local.json'
if (Test-Path -LiteralPath $destinoConfiguracion) { throw 'Ya existe lector.local.json. Revisarlo antes de reinstalar; no se sobrescribe.' }
$venvLector = Join-Path $PSScriptRoot '.venv'
if (-not (Test-Path -LiteralPath (Join-Path $venvLector 'Scripts\python.exe'))) {
    & $PythonExe -m venv $venvLector
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno virtual.' }
}
$pythonInstalado = Join-Path $venvLector 'Scripts\python.exe'
$argumentosPip = @('-m','pip','install','-r',(Join-Path $PSScriptRoot 'requirements-lock.txt'))
if ($RepositorioPaquetes) { $argumentosPip += @('--no-index','--find-links',$RepositorioPaquetes) }
& $pythonInstalado @argumentosPip
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias. Revisar conexion o repositorio de paquetes.' }
@{PythonExe='.venv\Scripts\python.exe';PopplerBin=[IO.Path]::GetFullPath($PopplerBin);HostEscucha='0.0.0.0';Puerto=8765;EquiposPermitidos=$EquiposPermitidos} |
    ConvertTo-Json | Set-Content -LiteralPath $destinoConfiguracion -Encoding UTF8
Write-Host 'Entorno instalado. Instalar/importar el modelo en Ollama antes de procesar PDFs. Ver README.md.'
