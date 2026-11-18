param(
    [Parameter(Mandatory=$true)][string]$IpLector,
    [Parameter(Mandatory=$true)][string]$IpSigap,
    [int]$Puerto = 8765
)
$ErrorActionPreference = 'Stop'
$nombreReglaLector = 'SIGAP-Lector-8765'
$existenteLector = Get-NetFirewallRule -Name $nombreReglaLector -ErrorAction SilentlyContinue
if ($existenteLector) {
    throw 'La regla SIGAP-Lector-8765 ya existe. Revisarla antes de modificarla.'
}
New-NetFirewallRule -Name $nombreReglaLector -DisplayName 'SIGAP - Lector de facturas PDF' `
    -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Puerto `
    -LocalAddress $IpLector -RemoteAddress $IpSigap -Profile Any | Out-Null
Write-Host ('Habilitado TCP '+$Puerto+' desde '+$IpSigap+' hacia '+$IpLector+'.')
