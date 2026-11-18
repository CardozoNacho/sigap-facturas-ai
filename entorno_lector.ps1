# Configuracion comun para los lanzadores actuales. No contiene credenciales.
function Get-EntornoLector {
    $raizEntorno = $PSScriptRoot
    $archivoEntorno = Join-Path $raizEntorno 'configuracion\lector.local.json'
    $configEntorno = @{}
    if (Test-Path -LiteralPath $archivoEntorno) {
        $objetoEntorno = Get-Content -Raw -LiteralPath $archivoEntorno | ConvertFrom-Json
        foreach ($propiedadEntorno in $objetoEntorno.PSObject.Properties) {
            $configEntorno[$propiedadEntorno.Name] = $propiedadEntorno.Value
        }
    }
    $pythonEntorno = $configEntorno['PythonExe']
    if ($pythonEntorno) {
        if (-not [IO.Path]::IsPathRooted($pythonEntorno)) { $pythonEntorno = Join-Path $raizEntorno $pythonEntorno }
    } else {
        $pythonEntorno = Join-Path $raizEntorno '.venv\Scripts\python.exe'
    }
    if (-not (Test-Path -LiteralPath $pythonEntorno)) { throw 'No se encontro Python. Ejecutar instalar_entorno.ps1 o configurar PythonExe.' }
    $popplerEntorno = $configEntorno['PopplerBin']
    if ($popplerEntorno) {
        if (-not [IO.Path]::IsPathRooted($popplerEntorno)) { $popplerEntorno = Join-Path $raizEntorno $popplerEntorno }
        if (-not (Test-Path -LiteralPath (Join-Path $popplerEntorno 'pdfinfo.exe'))) { throw 'PopplerBin no contiene pdfinfo.exe.' }
        $env:PATH = $popplerEntorno + ';' + $env:PATH
    }
    foreach ($programaEntorno in @('pdfinfo.exe','pdftoppm.exe')) {
        if (-not (Get-Command $programaEntorno -ErrorAction SilentlyContinue)) { throw ('Falta Poppler: ' + $programaEntorno) }
    }
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONNOUSERSITE = '1'
    $env:PYTHONHOME = $null
    $env:PYTHONPATH = $null
    [pscustomobject]@{
        PythonExe = [IO.Path]::GetFullPath($pythonEntorno)
        HostEscucha = $(if ($configEntorno['HostEscucha']) { $configEntorno['HostEscucha'] } else { '0.0.0.0' })
        Puerto = $(if ($configEntorno['Puerto']) { [int]$configEntorno['Puerto'] } else { 8765 })
        EquiposPermitidos = $(if ($configEntorno['EquiposPermitidos']) { $configEntorno['EquiposPermitidos'] } else { '127.0.0.1' })
    }
}
