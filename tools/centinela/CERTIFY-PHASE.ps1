param(
    [Parameter(Mandatory = $true)]
    [string]$Manifest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

$Repo = 'E:\Github\MoneyPrinterTurbo'
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
$Certifier = Join-Path $Repo 'tools\centinela\phase_certifier.py'

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python MPT no encontrado: $Python"
}
if (-not (Test-Path -LiteralPath $Certifier -PathType Leaf)) {
    throw "Phase certifier no encontrado: $Certifier"
}
if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) {
    throw "Phase manifest no encontrado: $Manifest"
}

Set-Location -LiteralPath $Repo

& $Python `
    $Certifier `
    --repo $Repo `
    --manifest $Manifest

if ($LASTEXITCODE -ne 0) {
    throw "CERTIFY-PHASE falló: ExitCode=$LASTEXITCODE"
}
