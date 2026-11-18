param(
    [string]$Pdf = '',
    [string]$MesExpediente = '',
    [string]$FechaEmision = '',
    [string]$NumeroExpediente = '',
    [int]$FolioInicial = 0,
    [int]$PaginaInicial = 0,
    [int]$PaginaFinal = 0,
    [string]$Salida = '',
    [switch]$Preparar
)
$ErrorActionPreference = 'Stop'
if (-not $Pdf) { $Pdf = Read-Host 'Ruta del PDF' }
if (-not $MesExpediente) { $MesExpediente = Read-Host 'Mes del expediente (MM/AAAA)' }
if (-not $FechaEmision) { $FechaEmision = Read-Host 'Fecha de emision asignada (DD/MM/AAAA)' }
if (-not $NumeroExpediente) { $NumeroExpediente = Read-Host 'Numero de expediente (ejemplo 90001/26)' }
if (-not $FolioInicial) { $FolioInicial = [int](Read-Host 'Folio de la primera factura') }
. (Join-Path $PSScriptRoot 'entorno_lector.ps1')
$entornoLote = Get-EntornoLector
$pythonLote = $entornoLote.PythonExe
$env:PYTHONIOENCODING = 'utf-8'
$argumentosLote = @((Join-Path $PSScriptRoot 'procesar_pdf.py'), $Pdf,
    '--mes', $MesExpediente, '--fecha-emision', $FechaEmision,
    '--expediente', $NumeroExpediente, '--folio-inicial', [string]$FolioInicial)
if ($PaginaInicial) { $argumentosLote += @('--pagina-inicial', [string]$PaginaInicial) }
if ($PaginaFinal) { $argumentosLote += @('--pagina-final', [string]$PaginaFinal) }
if ($Salida) { $argumentosLote += @('--salida', $Salida) }
if ($Preparar) { $argumentosLote += '--preparar' }
& $pythonLote @argumentosLote
exit $LASTEXITCODE
