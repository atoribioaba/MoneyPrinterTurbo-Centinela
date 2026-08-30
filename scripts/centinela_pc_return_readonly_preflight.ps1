#Requires -Version 5.1
<##
.SYNOPSIS
    Read-only evidence collector for the EL CENTINELA DEL UNIVERSO PC return.

.DESCRIPTION
    Collects Git, Windows, storage, NVIDIA/CUDA, FFmpeg, Python/uv and Ollama
    evidence without changing the repository, installing packages, starting
    services, pulling/rebasing/merging, modifying drivers, or deleting files.

    Output is written under %TEMP%, never inside the repository.
##>

[CmdletBinding()]
param(
    [string]$RepoPath = 'E:\Github\MoneyPrinterTurbo'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

$ExpectedBranch = 'centinela-cert/golden-real-e2e-v0.1'
$ExpectedHead = '186104539a7116ad48b96beac90eccd3c4c37801'
$ExpectedStashSha = '22ee99b0703be803e63beaed2370485c84604c9a'
$ExpectedStashLabel = 'C2.11O-M V34 pre-V33 preserve 20260826-172847'
$KnownUntracked = @(
    'app/services/centinela/quality/f57_real_runner.py',
    'test/services/test_f57_real_runner.py',
    'test/services/test_public_source_rights.py'
)

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$OutputDir = Join-Path $env:TEMP "Centinela_Preflight_$Stamp"
$ReportPath = Join-Path $OutputDir 'centinela-pc-return-preflight.txt'
$HashPath = Join-Path $OutputDir 'centinela-pc-return-preflight.sha256.txt'
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$script:ReportLines = @()

function Add-Line {
    param([AllowEmptyString()][string]$Text = '')
    $script:ReportLines += $Text
}

function Add-Section {
    param([string]$Title)
    Add-Line ''
    Add-Line ('=' * 78)
    Add-Line $Title
    Add-Line ('=' * 78)
}

function Invoke-Capture {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    Add-Line "--- $Name ---"
    try {
        $Text = (& $Action 2>&1 | Out-String -Width 4096).TrimEnd()
        if ([string]::IsNullOrWhiteSpace($Text)) {
            Add-Line '[NO OUTPUT]'
        }
        else {
            Add-Line $Text
        }
    }
    catch {
        Add-Line ("[ERROR] {0}" -f $_.Exception.Message)
    }
    Add-Line ''
}

function Command-Exists {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

Add-Line 'EL CENTINELA DEL UNIVERSO - PC RETURN READ-ONLY PREFLIGHT'
Add-Line ("Generated: {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss K'))
Add-Line ("Computer: {0}" -f $env:COMPUTERNAME)
Add-Line ("User: {0}" -f $env:USERNAME)
Add-Line ("RepoPath requested: {0}" -f $RepoPath)
Add-Line 'MODE=READ_ONLY_EVIDENCE_COLLECTION'
Add-Line 'NO_PULL=TRUE'
Add-Line 'NO_MERGE=TRUE'
Add-Line 'NO_REBASE=TRUE'
Add-Line 'NO_RESET=TRUE'
Add-Line 'NO_INSTALL=TRUE'
Add-Line 'NO_DRIVER_CHANGE=TRUE'
Add-Line 'NO_MODEL_DOWNLOAD=TRUE'

Add-Section '1. WINDOWS / CPU / RAM'
Invoke-Capture 'Windows OS' {
    Get-CimInstance Win32_OperatingSystem |
        Select-Object Caption, Version, BuildNumber, OSArchitecture,
            @{Name='TotalRAM_GiB';Expression={[math]::Round($_.TotalVisibleMemorySize / 1MB, 2)}},
            @{Name='FreeRAM_GiB';Expression={[math]::Round($_.FreePhysicalMemory / 1MB, 2)}} |
        Format-List
}
Invoke-Capture 'CPU' {
    Get-CimInstance Win32_Processor |
        Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed |
        Format-List
}
Invoke-Capture 'Video controllers' {
    Get-CimInstance Win32_VideoController |
        Select-Object Name, DriverVersion,
            @{Name='AdapterRAM_GiB';Expression={if ($_.AdapterRAM) {[math]::Round($_.AdapterRAM / 1GB, 2)} else {$null}}} |
        Format-Table -AutoSize
}

Add-Section '2. STORAGE / CANONICAL PATHS'
foreach ($DriveLetter in @('D', 'E')) {
    Invoke-Capture "Drive $DriveLetter volume" {
        Get-Volume -DriveLetter $DriveLetter -ErrorAction Stop |
            Select-Object DriveLetter, FileSystemLabel, FileSystem, HealthStatus,
                @{Name='Size_GiB';Expression={[math]::Round($_.Size / 1GB, 2)}},
                @{Name='Free_GiB';Expression={[math]::Round($_.SizeRemaining / 1GB, 2)}} |
            Format-List
    }
    Invoke-Capture "Drive $DriveLetter physical disk" {
        Get-Partition -DriveLetter $DriveLetter -ErrorAction Stop |
            Get-Disk -ErrorAction Stop |
            Select-Object Number, FriendlyName, BusType, MediaType,
                @{Name='Size_GiB';Expression={[math]::Round($_.Size / 1GB, 2)}} |
            Format-List
    }
}

$CanonicalPaths = @(
    'E:\Github\MoneyPrinterTurbo',
    'E:\IA\AstroMedia',
    'E:\IA\Qwen3-TTS',
    'D:\ASTRONOMÍA\Medios',
    'D:\ASTRONOMÍA\Medios\R9_Golden_Local'
)
foreach ($Path in $CanonicalPaths) {
    Add-Line ("PATH_EXISTS | {0} | {1}" -f (Test-Path -LiteralPath $Path), $Path)
}

Add-Section '3. GIT - PRESERVE BEFORE RECONCILIATION'
if (-not (Test-Path -LiteralPath $RepoPath -PathType Container)) {
    Add-Line "[BLOCKED] Repository path not found: $RepoPath"
}
elseif (-not (Command-Exists 'git')) {
    Add-Line '[BLOCKED] git is not available in PATH.'
}
else {
    Push-Location $RepoPath
    try {
        $ActualRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
        $ActualBranch = (& git branch --show-current 2>$null).Trim()
        $ActualHead = (& git rev-parse HEAD 2>$null).Trim()

        Add-Line ("GIT_ROOT={0}" -f $ActualRoot)
        Add-Line ("GIT_BRANCH={0}" -f $ActualBranch)
        Add-Line ("GIT_HEAD={0}" -f $ActualHead)
        Add-Line ("EXPECTED_BRANCH={0}" -f $ExpectedBranch)
        Add-Line ("EXPECTED_HEAD={0}" -f $ExpectedHead)
        Add-Line ("BRANCH_MATCH={0}" -f ($ActualBranch -eq $ExpectedBranch))
        Add-Line ("HEAD_MATCH={0}" -f ($ActualHead -eq $ExpectedHead))
        Add-Line ''

        Invoke-Capture 'git status --porcelain=v1 --branch' {
            & git status --porcelain=v1 --branch
        }
        Invoke-Capture 'git diff --name-status (unstaged)' {
            & git diff --name-status
        }
        Invoke-Capture 'git diff --cached --name-status (staged)' {
            & git diff --cached --name-status
        }
        Invoke-Capture 'git stash list with object IDs' {
            & git stash list '--format=%gd|%H|%gs'
        }

        $StashEvidence = (& git stash list '--format=%gd|%H|%gs' 2>$null | Out-String)
        Add-Line ("EXPECTED_STASH_SHA={0}" -f $ExpectedStashSha)
        Add-Line ("EXPECTED_STASH_LABEL={0}" -f $ExpectedStashLabel)
        Add-Line ("EXPECTED_STASH_SHA_FOUND={0}" -f ($StashEvidence -match [regex]::Escape($ExpectedStashSha)))
        Add-Line ("EXPECTED_STASH_LABEL_FOUND={0}" -f ($StashEvidence -match [regex]::Escape($ExpectedStashLabel)))
        Add-Line ''

        foreach ($RelativePath in $KnownUntracked) {
            $FullPath = Join-Path $RepoPath $RelativePath
            $Exists = Test-Path -LiteralPath $FullPath -PathType Leaf
            Add-Line ("KNOWN_LOCAL_FILE_EXISTS | {0} | {1}" -f $Exists, $RelativePath)
            if ($Exists) {
                try {
                    $Hash = (Get-FileHash -LiteralPath $FullPath -Algorithm SHA256 -ErrorAction Stop).Hash
                    Add-Line ("KNOWN_LOCAL_FILE_SHA256 | {0} | {1}" -f $Hash, $RelativePath)
                }
                catch {
                    Add-Line ("KNOWN_LOCAL_FILE_HASH_ERROR | {0} | {1}" -f $_.Exception.Message, $RelativePath)
                }
                $StatusLine = (& git status --porcelain=v1 -- $RelativePath 2>$null | Out-String).Trim()
                Add-Line ("KNOWN_LOCAL_FILE_GIT_STATUS | {0} | {1}" -f $StatusLine, $RelativePath)
            }
        }
    }
    finally {
        Pop-Location
    }
}

Add-Section '4. TOOLCHAIN VERSIONS'
foreach ($Tool in @('git', 'python', 'py', 'uv', 'ffmpeg', 'ffprobe', 'nvidia-smi', 'nvcc', 'ollama')) {
    $Command = Get-Command $Tool -ErrorAction SilentlyContinue
    if ($null -eq $Command) {
        Add-Line ("COMMAND_AVAILABLE | FALSE | {0}" -f $Tool)
    }
    else {
        Add-Line ("COMMAND_AVAILABLE | TRUE | {0} | {1}" -f $Tool, $Command.Source)
    }
}
Add-Line ''

if (Command-Exists 'git') { Invoke-Capture 'git --version' { & git --version } }
if (Command-Exists 'python') { Invoke-Capture 'python --version' { & python --version } }
if (Command-Exists 'py') { Invoke-Capture 'py -0p' { & py -0p } }
if (Command-Exists 'uv') { Invoke-Capture 'uv --version' { & uv --version } }
if (Command-Exists 'nvcc') { Invoke-Capture 'CUDA Toolkit nvcc --version' { & nvcc --version } }

Add-Section '5. NVIDIA DRIVER / GPU / CUDA VISIBILITY'
if (Command-Exists 'nvidia-smi') {
    Invoke-Capture 'nvidia-smi summary' { & nvidia-smi }
    Invoke-Capture 'nvidia-smi concise GPU query' {
        & nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,memory.free --format=csv,noheader,nounits
    }
}
else {
    Add-Line '[BLOCKED] nvidia-smi not available.'
}

Add-Section '6. FFMPEG / NVENC / LIBX264 AVAILABILITY'
if (Command-Exists 'ffmpeg') {
    Invoke-Capture 'ffmpeg -version' { & ffmpeg -hide_banner -version }
    Invoke-Capture 'ffmpeg relevant encoders' {
        & ffmpeg -hide_banner -encoders 2>&1 | Select-String -Pattern 'h264_nvenc|hevc_nvenc|libx264'
    }
    Invoke-Capture 'ffmpeg hardware accelerations' { & ffmpeg -hide_banner -hwaccels }
}
else {
    Add-Line '[BLOCKED] ffmpeg not available.'
}
if (Command-Exists 'ffprobe') { Invoke-Capture 'ffprobe -version' { & ffprobe -hide_banner -version } }

Add-Section '7. OLLAMA LOCAL RUNTIME - NO SERVICE START'
if (Command-Exists 'ollama') {
    Invoke-Capture 'ollama --version' { & ollama --version }
}
else {
    Add-Line '[INFO] ollama command not available.'
}
Invoke-Capture 'Ollama loopback /api/tags (only if already running)' {
    try {
        $Response = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -Method Get -TimeoutSec 2 -ErrorAction Stop
        $Response | ConvertTo-Json -Depth 8
    }
    catch {
        "OLLAMA_LOOPBACK_UNAVAILABLE={0}" -f $_.Exception.Message
    }
}

Add-Section '8. CANONICAL LOCAL COMPONENT PATH SNAPSHOT'
foreach ($Path in @('E:\IA\AstroMedia', 'E:\IA\Qwen3-TTS', 'D:\ASTRONOMÍA\Medios\R9_Golden_Local')) {
    Add-Line "--- $Path ---"
    if (Test-Path -LiteralPath $Path -PathType Container) {
        try {
            Get-ChildItem -LiteralPath $Path -Force -ErrorAction Stop |
                Select-Object Name, Length, LastWriteTime, Attributes |
                Format-Table -AutoSize |
                Out-String -Width 4096 |
                ForEach-Object { Add-Line $_.TrimEnd() }
        }
        catch {
            Add-Line ("[ERROR] {0}" -f $_.Exception.Message)
        }
    }
    else {
        Add-Line '[NOT FOUND]'
    }
    Add-Line ''
}

Add-Section '9. PREFLIGHT INTERPRETATION'
Add-Line 'This script has not certified CUDA execution, NVENC encoding, Qwen3-TTS quality, Whisper alignment, AstroMedia correctness, F57 local 8/8, Golden E2E, or Publication Package readiness.'
Add-Line 'It only captures the initial state needed before selective reconciliation and real certification.'
Add-Line 'DO_NOT_MERGE_FROM_THIS_REPORT=TRUE'
Add-Line 'DO_NOT_FREEZE_FROM_THIS_REPORT=TRUE'
Add-Line 'AUTO_PUBLICATION=FALSE'

$script:ReportLines | Set-Content -LiteralPath $ReportPath -Encoding UTF8
$ReportHash = (Get-FileHash -LiteralPath $ReportPath -Algorithm SHA256).Hash
("{0}  {1}" -f $ReportHash, (Split-Path $ReportPath -Leaf)) | Set-Content -LiteralPath $HashPath -Encoding ASCII

Write-Host "PREFLIGHT_REPORT=$ReportPath"
Write-Host "PREFLIGHT_SHA256=$ReportHash"
Write-Host "PREFLIGHT_HASH_FILE=$HashPath"
Write-Host 'PREFLIGHT_COMPLETE=TRUE'
