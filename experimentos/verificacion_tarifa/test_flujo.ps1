# Prueba del programa completo con respuestas simuladas: no consulta Ollama.
$ErrorActionPreference = 'Stop'
$raiz = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$lector = Join-Path $raiz 'lectores\general\lector_qwen_tarifa_verificada.ps1'
$tokens=$null; $errores=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($lector,[ref]$tokens,[ref]$errores)
$fuente=[IO.File]::ReadAllText($lector)
$funcion=$ast.FindAll({param($n)
    $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-Lectura'
},$false) | Select-Object -First 1
$simulada=@'
function Invoke-Lectura($Etapa, $Imagen, $Instrucciones, $Esquema) {
    $script:etapasSimuladas += $Etapa
    switch -Wildcard ($Etapa) {
        'frente-general-*' { return [pscustomobject]@{numero_comprobante='12345678';nfact='123456789012';nisnu='123456789';importepvenc='1.000,00';consactual='456';tarifa=$script:casoSimulado.general} }
        'tarifa-verificacion-*' { return [pscustomobject]@{texto_tarifa=$script:casoSimulado.recorte} }
        'tarifa-desempate-*' { return [pscustomobject]@{texto_tarifa=$script:casoSimulado.desempate} }
        'nfact-*' { return [pscustomobject]@{nfact='123456789012'} }
        'consumo-t1-*' { return [pscustomobject]@{consactual='1234'} }
        'consumo' { return [pscustomobject]@{consactual='2016'} }
        'factor-t1' { return [pscustomobject]@{texto="Informacion al Cliente`nTIPO DE USO: Oficial Municipal TARIFA 1`nNO REGISTRA DEUDA"} }
        'dorso' {
            $r=[ordered]@{}
            foreach($k in $Esquema.properties.Keys) { $r[$k]='4' }
            return [pscustomobject]$r
        }
        default { throw "Etapa inesperada: $Etapa" }
    }
}
'@
$fuente=$fuente.Replace($funcion.Extent.Text,$simulada)
$asignacion=$ast.FindAll({param($n)
    $n -is [Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq '$raizProyecto'
},$false) | Select-Object -First 1
$fuente=$fuente.Replace($asignacion.Extent.Text,('$raizProyecto = ''' + $raiz.Replace("'","''") + "'"))
$fuente=$fuente.Replace('$PSScriptRoot',("'" + (Split-Path $lector -Parent).Replace("'","''") + "'"))
$casos=@(
    @{nombre='corrige_1_a_4';general=1;recorte='Tarifa 4-Alum.Pub.';desempate='Tarifa 4-Alum.Pub.';esperada=4;consumo='2016'},
    @{nombre='corrige_3_a_4';general=3;recorte='Tarifa 4-Alum.Pub.';desempate='Tarifa 4-Alum.Pub.';esperada=4;consumo='2016'},
    @{nombre='corrige_4_a_1';general=4;recorte='Tarifa 1-Uso General';desempate='Tarifa 1-Uso General';esperada=1;consumo='1234'},
    @{nombre='conserva_t1';general=1;recorte='Tarifa 1-Uso General';desempate=$null;esperada=1;consumo='456'},
    @{nombre='conserva_t2';general=2;recorte='Tarifa 2-Medianas Demandas';desempate=$null;esperada=2;consumo='2016'},
    @{nombre='conserva_t3';general=3;recorte='Tarifa 3-G.D.';desempate=$null;esperada=3;consumo='2016'},
    @{nombre='tres_distintas';general=1;recorte='Tarifa 4-Alum.Pub.';desempate='Tarifa 3-G.D.';esperada=$null;consumo=$null},
    @{nombre='general_null';general=$null;recorte='Tarifa 4-Alum.Pub.';desempate='Tarifa 4-Alum.Pub.';esperada=4;consumo='2016'},
    @{nombre='recorte_null';general=4;recorte=$null;desempate='Tarifa 4-Alum.Pub.';esperada=$null;consumo=$null}
)
$base=Join-Path $raiz ('output\test_flujo_tarifa_' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
foreach($script:casoSimulado in $casos) {
    $script:etapasSimuladas=@()
    $salidaCaso=Join-Path $base $script:casoSimulado.nombre
    New-Item -ItemType Directory -Path $salidaCaso -Force | Out-Null
    $frenteCaso=Join-Path $salidaCaso 'frente.png'
    $dorsoCaso=Join-Path $salidaCaso 'dorso.png'
    Add-Type -AssemblyName System.Drawing
    $imagenSintetica = New-Object Drawing.Bitmap(1275, 1650)
    $graficoSintetico = [Drawing.Graphics]::FromImage($imagenSintetica)
    try {
        $graficoSintetico.Clear([Drawing.Color]::White)
        $imagenSintetica.Save($frenteCaso, [Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $graficoSintetico.Dispose()
        $imagenSintetica.Dispose()
    }
    if ($script:casoSimulado.esperada -in @(2,3,4)) {
        Copy-Item -LiteralPath $frenteCaso -Destination $dorsoCaso
    }
    & ([scriptblock]::Create($fuente)) -FechaEmision '18/06/2026' -NumeroExpediente 'PRUEBA' -FolioAsignado 1 -MesExpediente '06/2026' -FrenteImagen $frenteCaso -DorsoImagen $dorsoCaso -DirectorioSalida $salidaCaso | Out-Null
    $leida=Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $salidaCaso 'lectura-con-nfact-validado.json') | ConvertFrom-Json
    if ($leida.tarifa -ne $script:casoSimulado.esperada) { throw 'Tarifa final inesperada.' }
    if ($leida.consactual -ne $script:casoSimulado.consumo) { throw 'Consumo de rama anterior o faltante.' }
    if ($null -eq $leida.tarifa) {
        if (@($script:etapasSimuladas | Where-Object { $_ -match '^(consumo|dorso|factor-t1)' }).Count) { throw 'Se eligio una rama sin confirmar tarifa.' }
    } elseif ($leida.tarifa -eq 1) {
        if ($script:etapasSimuladas -contains 'dorso' -or (Test-Path -LiteralPath $dorsoCaso)) { throw 'T1 no debe abrir ni renderizar dorso.' }
    } else {
        if ($script:etapasSimuladas -notcontains 'dorso' -or $script:etapasSimuladas -notcontains 'consumo') { throw 'No se leyo la rama corregida.' }
        $esperados=switch($leida.tarifa) {
            2 { @('factpot','recfactpot','ptapotconv','ptapotreg') }
            3 { @('factpot','recfactpot','fptapotconv','fptapotreg','fptapotconve','fptapotregi') }
            4 { @('t4potconv') }
        }
        $extras=@($leida.PSObject.Properties.Name | Where-Object { $_ -match '^(factpot|recfactpot|ptapot|fptapot|t4pot)' })
        if (Compare-Object @($extras | Sort-Object) @($esperados | Sort-Object)) { throw 'Campos de otra tarifa en resultado.' }
    }
}
Write-Host '9 recorridos completos correctos con respuestas simuladas; sin llamadas a Ollama.'
