$ErrorActionPreference = 'Stop'
$raiz = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$lector = Join-Path $raiz 'lectores\general\lector_qwen_tarifa_verificada.ps1'
$tokens=$null; $errores=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($lector,[ref]$tokens,[ref]$errores)
if ($errores.Count) { throw ($errores | Out-String) }
foreach ($funcion in $ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)) {
    . ([scriptblock]::Create($funcion.Extent.Text))
}
function Assert-Igual($Real,$Esperado,$Nombre) {
    if ($null -eq $Esperado) { if ($null -ne $Real) { throw "$Nombre no quedo null" } }
    elseif ($Real -cne $Esperado) { throw "$Nombre esperado=$Esperado real=$Real" }
}
Assert-Igual (Get-TarifaDesdeTexto 'Tarifa 4-Alum.Pub. c/medidor') 4 'T4'
Assert-Igual (Get-TarifaDesdeTexto 'Tarifa 1 - Uso General') 1 'T1'
Assert-Igual (Get-TarifaDesdeTexto 'Tarifa 2 - Medianas Demandas') 2 'T2'
Assert-Igual (Get-TarifaDesdeTexto 'Tarifa 3 - G.D. Vinc. Inf. BT') 3 'T3'
Assert-Igual (Get-TarifaDesdeTexto '2026 5 4') $null 'Sin rotulo'
Assert-Igual (Get-TarifaDesdeTexto 'Tarifa 14') $null 'Dos digitos'
Assert-Igual (Get-TarifaDesdeTexto 'Tarifa 5') $null 'Fuera de rango'
Assert-Igual (Get-TarifaDesdeTexto 'Tarifa 1 Tarifa 4') $null 'Ambigua'
Assert-Igual (Get-TarifaDesdeTexto $null) $null 'Ausente'
Assert-Igual (Resolve-TarifaVerificada 4 4 $null).tarifa 4 'Acuerdo'
Assert-Igual (Resolve-TarifaVerificada 1 4 4).tarifa 4 'Corrige T1 falsa'
Assert-Igual (Resolve-TarifaVerificada 3 4 4).tarifa 4 'Corrige T3 falsa'
Assert-Igual (Resolve-TarifaVerificada 4 1 1).tarifa 1 'Corrige a T1'
Assert-Igual (Resolve-TarifaVerificada 1 4 3).tarifa $null 'Tres distintas'
Assert-Igual (Resolve-TarifaVerificada 1 4 1).tarifa $null 'No imponer general contra recorte'
Assert-Igual (Resolve-TarifaVerificada 4 $null 4).tarifa $null 'Recorte ilegible'
Assert-Igual (Resolve-TarifaVerificada $null 3 3).tarifa 3 'General ilegible'
$base = Join-Path $raiz 'lectores\general\lector_qwen.ps1'
if ((Get-FileHash -LiteralPath $base -Algorithm SHA256).Hash -ne '45D895FEDC33F18EB5E434E3FBF51BFFE38687AD68560615E2CF5A458C15362C') { throw 'Cambio la referencia historica.' }
$astBase=[Management.Automation.Language.Parser]::ParseFile($base,[ref]$tokens,[ref]$errores)
foreach($nombre in @('Get-ConfiguracionDorso','New-RecorteDorso','Confirmar-NumeroFactura','Get-FactorT1DesdeTexto','New-RecorteConsumo')) {
    $original=$astBase.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $nombre},$false) | Select-Object -First 1
    $nuevo=$ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $nombre},$false) | Select-Object -First 1
    Assert-Igual ($nuevo.Extent.Text.Replace("`r`n","`n")) ($original.Extent.Text.Replace("`r`n","`n")) "Funcion conservada $nombre"
}
Write-Host '17 reglas, hash de referencia y 5 funciones criticas conservadas: correctos.'
