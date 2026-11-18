param([string]$PythonExe = '', [switch]$Verificar)
$ErrorActionPreference = 'Stop'
$destino = Join-Path $env:LOCALAPPDATA 'SIGAP\RCC\programa'
function Invoke-RccPython {
    param([string]$ExecutableRcc, [string[]]$ArgumentsRcc)
    $previousPreferenceRcc = $ErrorActionPreference
    try {
        # PowerShell 5.1 puede tratar stderr de un launcher como error terminante.
        $ErrorActionPreference = 'Continue'
        $outputRcc = & $ExecutableRcc @ArgumentsRcc 2>$null
        $codeRcc = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreferenceRcc }
    return [pscustomobject]@{ Code = $codeRcc; Output = $outputRcc }
}
$probe = @'
import sys, json, struct, importlib.util
info = {'version': '.'.join(map(str, sys.version_info[:3])), 'executable': sys.executable, 'bits': struct.calcsize('P') * 8}
try:
    import tkinter
    info['tk'] = str(tkinter.TkVersion)
except Exception:
    info['tk'] = None
info['venv'] = importlib.util.find_spec('venv') is not None and importlib.util.find_spec('ensurepip') is not None
info['ok'] = sys.version_info >= (3, 10) and info['bits'] == 64 and bool(info['tk']) and info['venv']
print(json.dumps(info))
'@

$candidatos = New-Object 'System.Collections.Generic.List[string]'
if ($PythonExe) {
    $candidatos.Add($PythonExe)
} else {
    # Primero instalaciones registradas; evita elegir un alias de Microsoft Store sin Python instalado.
    foreach ($key in @('HKCU:\Software\Python\PythonCore','HKLM:\SOFTWARE\Python\PythonCore','HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore')) {
        if (Test-Path -LiteralPath $key) {
            foreach ($versionKey in Get-ChildItem -LiteralPath $key) {
                $installKey = Join-Path $versionKey.PSPath 'InstallPath'
                if (Test-Path -LiteralPath $installKey) {
                    $registro = Get-Item -LiteralPath $installKey
                    $exe = $registro.GetValue('ExecutablePath')
                    if (-not $exe -and $registro.GetValue('')) { $exe = Join-Path $registro.GetValue('') 'python.exe' }
                    if ($exe) { $candidatos.Add($exe) }
                }
            }
        }
    }
    foreach ($name in @('python.exe','python3.exe')) {
        $pythonCmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($pythonCmd) { $candidatos.Add($pythonCmd.Source) }
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($tag in @('-3.14','-3.13','-3.12','-3.11','-3.10')) {
            $detected = Invoke-RccPython -ExecutableRcc $launcher.Source -ArgumentsRcc @($tag,'-c','import sys; print(sys.executable)')
            if ($detected.Code -eq 0 -and $detected.Output) { $candidatos.Add(($detected.Output | Select-Object -Last 1).Trim()) }
        }
    }
}

$diagnosticos = New-Object 'System.Collections.Generic.List[string]'
$seleccion = $null
foreach ($candidato in ($candidatos | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $candidato -PathType Leaf)) { continue }
    try {
        $raw = Invoke-RccPython -ExecutableRcc $candidato -ArgumentsRcc @('-c',$probe)
        if ($raw.Code -ne 0) { continue }
        $info = ($raw.Output -join "`n") | ConvertFrom-Json
        $diagnosticos.Add(('Python {0}, {1} bits, Tcl/Tk: {2}, venv/pip: {3}' -f $info.version,$info.bits,[bool]$info.tk,$info.venv))
        if ($info.ok) { $seleccion = $info; break }
    } catch { $diagnosticos.Add('No se pudo comprobar un candidato Python.') }
}
if (-not $seleccion) {
    foreach ($detalle in $diagnosticos) { Write-Output $detalle }
    throw 'Se necesita Python 3.10 o posterior de 64 bits con Tcl/Tk y venv/pip. Instale desde python.org o indique -PythonExe RUTA. El lector PDF no se modifica.'
}
$PythonExe = $seleccion.executable
Write-Output ('Python seleccionado: {0} ({1} bits), Tcl/Tk {2}' -f $seleccion.version,$seleccion.bits,$seleccion.tk)
Write-Output ('Ejecutable: ' + $PythonExe)
if ($Verificar) { Write-Output 'Verificacion correcta. No se instalaron ni modificaron archivos.'; exit 0 }

New-Item -ItemType Directory -Path $destino -Force | Out-Null
$archivos = @('rcc_bridge.py','rcc_browser.py','rcc_contract.py','rcc_vault.py','configurar.py','requirements.txt','iniciar.cmd','configurar.cmd','README.md')
foreach ($nombre in $archivos) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot $nombre) -Destination (Join-Path $destino $nombre) -Force }
$venv = Join-Path $destino '.venv'
& $PythonExe -m venv $venv
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno RCC.' }
$pythonRcc = Join-Path $venv 'Scripts\python.exe'
& $pythonRcc -m pip install -r (Join-Path $destino 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias. Compruebe la conexion.' }
& $pythonRcc -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar Chromium.' }
$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
foreach ($item in @(@('SIGAP RCC','iniciar.cmd'),@('Configurar SIGAP RCC','configurar.cmd'))) {
    $shortcut = $shell.CreateShortcut((Join-Path $desktop ($item[0] + '.lnk')))
    $shortcut.TargetPath = Join-Path $destino $item[1]
    $shortcut.WorkingDirectory = $destino
    $shortcut.Save()
}
Write-Output 'Instalado. Abra Configurar SIGAP RCC, guarde URL SIGAP y credenciales RCC; luego abra SIGAP RCC.'
