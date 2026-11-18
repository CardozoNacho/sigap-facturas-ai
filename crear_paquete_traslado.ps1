param([string]$Destino = '')
$ErrorActionPreference = 'Stop'
if (-not $Destino) { $Destino = Join-Path $PSScriptRoot ('output\distribucion\sigap-lector-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.zip') }
$Destino = [IO.Path]::GetFullPath($Destino)
if (Test-Path -LiteralPath $Destino) { throw 'El ZIP de destino ya existe; no se sobrescribe.' }
$stagingPaquete = Join-Path $PSScriptRoot ('output\distribucion\preparacion-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stagingPaquete -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path $Destino -Parent) -Force | Out-Null
# Lista explicita: no copiar datos de usuarios, tokens, modelos, work ni .venv.
$archivosPaquete = @(
    'README.md','requirements.txt','requirements-lock.txt','.gitignore',
    'entorno_lector.ps1','instalar_entorno.ps1','verificar_instalacion.ps1',
    'crear_paquete_traslado.ps1','iniciar_servicio_lector.ps1','iniciar_servicio_automatico.ps1',
    'configurar_inicio_servicio.ps1','habilitar_firewall_lector.ps1',
    'servicio_lector.py','ejecutar_lote_servicio.py','procesar_pdf.py','procesar_pdf.ps1','evaluar_pdf.py',
    'configuracion\lector.ejemplo.json','lectores\general\lector_qwen.ps1',
    'lectores\general\lector_qwen_tarifa_verificada.ps1'
)
foreach ($carpetaPaquete in @('src','docs','despliegue')) {
    $archivosPaquete += @(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot $carpetaPaquete) -File -Recurse |
        Where-Object { $_.Extension -in @('.py','.md','.sql','.json') -and $_.FullName -notmatch '[\\/]__pycache__[\\/]' } |
        ForEach-Object { $_.FullName.Substring($PSScriptRoot.Length+1) })
}
foreach ($relativoPaquete in $archivosPaquete) {
    $copiaPaquete = Join-Path $stagingPaquete $relativoPaquete
    New-Item -ItemType Directory -Path (Split-Path $copiaPaquete -Parent) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $relativoPaquete) -Destination $copiaPaquete
}
$inventarioPaquete = foreach ($relativoPaquete in $archivosPaquete) {
    [pscustomobject]@{archivo=$relativoPaquete;sha256=(Get-FileHash -LiteralPath (Join-Path $stagingPaquete $relativoPaquete) -Algorithm SHA256).Hash}
}
$inventarioPaquete | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $stagingPaquete 'manifest_archivos.json') -Encoding UTF8
Compress-Archive -Path (Join-Path $stagingPaquete '*') -DestinationPath $Destino
Write-Host ('Paquete creado: '+$Destino)
Write-Host 'No incluye pesos, instaladores externos, PDFs, resultados, credenciales ni WAR de SIGAP. La preparacion se conserva en output/distribucion.'
