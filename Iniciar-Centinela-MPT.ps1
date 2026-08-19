$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$WebuiBat = Join-Path $ProjectRoot "webui.bat"

if (-not (Test-Path $WebuiBat)) {
    throw "No existe webui.bat en $ProjectRoot"
}

$ExistingMpt = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match '(?i)\bstreamlit\b' -and
            $_.CommandLine -match '(?i)webui[\\/]+Main\.py'
        }
)

if ($ExistingMpt.Count -gt 0) {
    Write-Host "MPT_WEBUI_RUNNING=True"

    $ExistingListener = @(
        Get-NetTCPConnection `
            -State Listen `
            -ErrorAction SilentlyContinue |
            Where-Object {
                $_.LocalAddress -eq "127.0.0.1" -and
                $_.LocalPort -ge 8501 -and
                $_.LocalPort -le 8599
            } |
            Select-Object -First 1
    )

    if ($ExistingListener.Count -gt 0) {
        Write-Host "MPT_WEBUI_PORT=$($ExistingListener[0].LocalPort)"
    }

    Write-Host "MPT_START_RESULT=ALREADY_RUNNING"
    exit 0
}

$Occupied8501 = @(
    Get-NetTCPConnection `
        -State Listen `
        -LocalPort 8501 `
        -ErrorAction SilentlyContinue
)

if ($Occupied8501.Count -gt 0) {
    throw "El puerto 8501 está ocupado por otro proceso. No se inicia MPT."
}

Write-Host "MPT_STARTING=True"

$Launcher = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList "/c", "`"$WebuiBat`"" `
    -WorkingDirectory $ProjectRoot `
    -PassThru

Write-Host "MPT_LAUNCHER_PID=$($Launcher.Id)"

$Healthy = $false

for ($Attempt = 1; $Attempt -le 30; $Attempt++) {

    Start-Sleep -Seconds 1

    try {
        $Health = Invoke-WebRequest `
            -Uri "http://127.0.0.1:8501/_stcore/health" `
            -UseBasicParsing `
            -TimeoutSec 2 `
            -ErrorAction Stop

        if (
            $Health.StatusCode -eq 200 -and
            $Health.Content.Trim() -eq "ok"
        ) {
            $Healthy = $true
            break
        }
    }
    catch {
        # Streamlit puede necesitar varios segundos para iniciar.
    }
}

if (-not $Healthy) {
    Write-Host "MPT_START_RESULT=FAILED"
    throw "MPT no respondió correctamente en 127.0.0.1:8501."
}

$Listener = Get-NetTCPConnection `
    -State Listen `
    -LocalAddress "127.0.0.1" `
    -LocalPort 8501 `
    -ErrorAction Stop |
    Select-Object -First 1

Write-Host "MPT_WEBUI_RUNNING=True"
Write-Host "MPT_WEBUI_ADDRESS=http://127.0.0.1:8501"
Write-Host "MPT_WEB_PID=$($Listener.OwningProcess)"
Write-Host "MPT_HEALTH=ok"
Write-Host "MPT_START_RESULT=OK"
