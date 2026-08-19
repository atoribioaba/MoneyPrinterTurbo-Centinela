$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd("\")
$VenvPython  = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$WebuiBat    = Join-Path $ProjectRoot "webui.bat"

function Get-CentinelaProcess {
    param(
        [int]$ProcessId
    )

    Get-CimInstance Win32_Process `
        -Filter "ProcessId=$ProcessId" `
        -ErrorAction SilentlyContinue
}

function Test-CentinelaStreamlit {
    param(
        $Process
    )

    if (-not $Process -or -not $Process.CommandLine) {
        return $false
    }

    if (
        $Process.CommandLine -notmatch '(?i)\bstreamlit\b' -or
        $Process.CommandLine -notmatch '(?i)webui[\\/]+Main\.py'
    ) {
        return $false
    }

    # Caso 1: proceso lanzado directamente por el Python del venv.
    if (
        $Process.ExecutablePath -and
        [System.IO.Path]::GetFullPath($Process.ExecutablePath) -eq
        [System.IO.Path]::GetFullPath($VenvPython)
    ) {
        return $true
    }

    # Caso 2: intérprete base hijo del launcher Python del venv.
    $Parent = Get-CentinelaProcess -ProcessId $Process.ParentProcessId

    if (
        $Parent -and
        $Parent.ExecutablePath -and
        [System.IO.Path]::GetFullPath($Parent.ExecutablePath) -eq
        [System.IO.Path]::GetFullPath($VenvPython) -and
        $Parent.CommandLine -match '(?i)\bstreamlit\b' -and
        $Parent.CommandLine -match '(?i)webui[\\/]+Main\.py'
    ) {
        return $true
    }

    # Caso 3: Streamlit cuyo padre fue iniciado por nuestro webui.bat.
    if (
        $Parent -and
        $Parent.CommandLine -and
        $Parent.CommandLine.IndexOf(
            $WebuiBat,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    ) {
        return $true
    }

    return $false
}


$AllProcesses = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match '(?i)\bstreamlit\b' -and
            $_.CommandLine -match '(?i)webui[\\/]+Main\.py'
        }
)

$Targets = @(
    $AllProcesses |
        Where-Object {
            Test-CentinelaStreamlit -Process $_
        }
)

if ($Targets.Count -eq 0) {
    Write-Host "MPT_WEBUI_RUNNING=False"
    Write-Host "MPT_STOP_RESULT=NOT_RUNNING"
    exit 0
}

Write-Host "=== PROCESOS MPT IDENTIFICADOS ==="

foreach ($Target in $Targets) {
    Write-Host (
        "PID={0} PARENT={1} EXE={2}" -f `
        $Target.ProcessId,
        $Target.ParentProcessId,
        $Target.ExecutablePath
    )
}


# Primero detenemos cualquier proceso identificado que posea
# directamente un puerto WebUI 8501-8599.
$ListenerPids = @(
    Get-NetTCPConnection `
        -State Listen `
        -ErrorAction SilentlyContinue |
        Where-Object {
            $_.LocalPort -ge 8501 -and
            $_.LocalPort -le 8599
        } |
        Select-Object -ExpandProperty OwningProcess -Unique
)

$TargetIds = @(
    $Targets |
        Select-Object -ExpandProperty ProcessId -Unique
)

foreach ($ListenerPid in $ListenerPids) {
    if ($TargetIds -contains $ListenerPid) {
        Write-Host "Deteniendo listener MPT PID=$ListenerPid"
        Stop-Process -Id $ListenerPid -Force -ErrorAction SilentlyContinue
    }
}

Start-Sleep -Milliseconds 500


# Después cerramos launchers Streamlit restantes del mismo proyecto.
foreach ($TargetId in $TargetIds) {
    if (Get-Process -Id $TargetId -ErrorAction SilentlyContinue) {
        Write-Host "Deteniendo proceso MPT PID=$TargetId"
        Stop-Process -Id $TargetId -Force -ErrorAction SilentlyContinue
    }
}

Start-Sleep -Milliseconds 500


# Limpia únicamente el cmd.exe que esté ejecutando ESTE webui.bat.
$CmdProcesses = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -ieq "cmd.exe" -and
            $_.CommandLine -and
            $_.CommandLine.IndexOf(
                $WebuiBat,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -ge 0
        }
)

foreach ($CmdProcess in $CmdProcesses) {
    Write-Host "Deteniendo launcher webui.bat PID=$($CmdProcess.ProcessId)"
    Stop-Process `
        -Id $CmdProcess.ProcessId `
        -Force `
        -ErrorAction SilentlyContinue
}


Start-Sleep -Milliseconds 500

$Remaining = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            Test-CentinelaStreamlit -Process $_
        }
)

if ($Remaining.Count -gt 0) {
    Write-Host "MPT_STOP_RESULT=INCOMPLETE"
    foreach ($Process in $Remaining) {
        Write-Host "REMAINING_PID=$($Process.ProcessId)"
    }
    exit 1
}

Write-Host "MPT_WEBUI_RUNNING=False"
Write-Host "MPT_STOP_RESULT=OK"
