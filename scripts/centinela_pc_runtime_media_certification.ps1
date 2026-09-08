#Requires -Version 5.1
<##
.SYNOPSIS
    Non-destructive physical media runtime certification for El Centinela.

.DESCRIPTION
    Run ONLY after the PC-return read-only preflight has been reviewed and the
    repository state has been safely reconciled. This script does not install,
    update, download, mutate Git state, start publication services, or touch
    project media. It creates synthetic video artifacts only under %TEMP% (or
    -OutputRoot), probes them, hashes them, and records NVIDIA/FFmpeg evidence.

    A successful h264_nvenc synthetic encode is evidence that this FFmpeg build,
    the installed NVIDIA driver and the physical NVENC path can cooperate. It is
    not evidence of CUDA use by unrelated Python/AI dependencies.
##>

[CmdletBinding()]
param(
    [string]$OutputRoot = $env:TEMP,
    [ValidateRange(1, 10)][int]$DurationSeconds = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:Lines = @()
$script:Blockers = @()
$script:Warnings = @()

function Add-Line {
    param([AllowEmptyString()][string]$Text = '')
    $script:Lines += $Text
}

function Add-Blocker {
    param([string]$Code, [string]$Message)
    $script:Blockers += $Code
    Add-Line ("[BLOCKER] {0} | {1}" -f $Code, $Message)
}

function Add-Warning {
    param([string]$Code, [string]$Message)
    $script:Warnings += $Code
    Add-Line ("[WARNING] {0} | {1}" -f $Code, $Message)
}

function Bool-Text {
    param([bool]$Value)
    if ($Value) { return 'TRUE' }
    return 'FALSE'
}

function Get-Application {
    param([string]$Name)
    return Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function ConvertTo-NativeArgument {
    param([AllowEmptyString()][string]$Value)
    if ([string]::IsNullOrEmpty($Value)) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    if ($Value.Contains('"')) { throw 'Unsupported quote in native argument.' }
    $Escaped = $Value -replace '(\\+)$', '${1}${1}'
    return '"' + $Escaped + '"'
}

function Invoke-Native {
    param([string]$Executable, [string[]]$Arguments = @())
    $Info = New-Object System.Diagnostics.ProcessStartInfo
    $Info.FileName = $Executable
    $Info.UseShellExecute = $false
    $Info.RedirectStandardOutput = $true
    $Info.RedirectStandardError = $true
    $Info.CreateNoWindow = $true
    $Info.Arguments = (($Arguments | ForEach-Object {
        ConvertTo-NativeArgument ([string]$_)
    }) -join ' ')

    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $Info
    try {
        [void]$Process.Start()
        $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
        $StderrTask = $Process.StandardError.ReadToEndAsync()
        $Process.WaitForExit()
        return [pscustomobject]@{
            ExitCode = [int]$Process.ExitCode
            Stdout = $StdoutTask.GetAwaiter().GetResult().TrimEnd()
            Stderr = $StderrTask.GetAwaiter().GetResult().TrimEnd()
            Success = ($Process.ExitCode -eq 0)
        }
    }
    finally {
        $Process.Dispose()
    }
}

function Add-NativeResult {
    param([string]$Name, [psobject]$Result)
    Add-Line ("--- {0} ---" -f $Name)
    Add-Line ("EXIT_CODE={0}" -f $Result.ExitCode)
    Add-Line ("SUCCESS={0}" -f (Bool-Text $Result.Success))
    if (-not [string]::IsNullOrWhiteSpace($Result.Stdout)) {
        Add-Line 'STDOUT:'
        Add-Line $Result.Stdout
    }
    if (-not [string]::IsNullOrWhiteSpace($Result.Stderr)) {
        Add-Line 'STDERR:'
        Add-Line $Result.Stderr
    }
}

function Get-Sha256Hex {
    param([string]$LiteralPath)
    return (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Invoke-EncodeProbe {
    param(
        [string]$Label,
        [string]$Codec,
        [string]$FfmpegPath,
        [string]$FfprobePath,
        [string]$OutputFile,
        [int]$Duration
    )

    $Arguments = @(
        '-hide_banner', '-y',
        '-f', 'lavfi',
        '-i', 'testsrc2=size=1080x1920:rate=30',
        '-t', [string]$Duration,
        '-an',
        '-c:v', $Codec,
        '-pix_fmt', 'yuv420p',
        $OutputFile
    )
    $Encode = Invoke-Native $FfmpegPath $Arguments
    Add-NativeResult ("ENCODE_{0}" -f $Label) $Encode

    if (-not $Encode.Success) {
        return [pscustomobject]@{
            Success = $false
            ProbeSuccess = $false
            Sha256 = ''
            FileSize = 0
        }
    }
    if (-not (Test-Path -LiteralPath $OutputFile -PathType Leaf)) {
        Add-Blocker ("{0}_OUTPUT_MISSING" -f $Label) 'FFmpeg returned success but output is missing.'
        return [pscustomobject]@{
            Success = $false
            ProbeSuccess = $false
            Sha256 = ''
            FileSize = 0
        }
    }

    $Item = Get-Item -LiteralPath $OutputFile
    if ($Item.Length -le 0) {
        Add-Blocker ("{0}_OUTPUT_EMPTY" -f $Label) 'Encoded output is empty.'
        return [pscustomobject]@{
            Success = $false
            ProbeSuccess = $false
            Sha256 = ''
            FileSize = 0
        }
    }

    $Probe = Invoke-Native $FfprobePath @(
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name,width,height,r_frame_rate,pix_fmt',
        '-show_entries', 'format=duration,size',
        '-of', 'json',
        $OutputFile
    )
    Add-NativeResult ("PROBE_{0}" -f $Label) $Probe

    $Hash = Get-Sha256Hex $OutputFile
    Add-Line ("{0}_FILE={1}" -f $Label, $OutputFile)
    Add-Line ("{0}_BYTES={1}" -f $Label, $Item.Length)
    Add-Line ("{0}_SHA256={1}" -f $Label, $Hash)

    return [pscustomobject]@{
        Success = $true
        ProbeSuccess = $Probe.Success
        Sha256 = $Hash
        FileSize = [long]$Item.Length
    }
}

$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$OutputDir = Join-Path $OutputRoot ("centinela-runtime-media-cert-{0}" -f $Timestamp)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$ReportPath = Join-Path $OutputDir 'runtime-media-certification.txt'
$HashPath = Join-Path $OutputDir 'runtime-media-certification.sha256.txt'
$NvencFile = Join-Path $OutputDir 'nvenc-1080x1920-30.mp4'
$X264File = Join-Path $OutputDir 'x264-1080x1920-30.mp4'

Add-Line 'EL CENTINELA DEL UNIVERSO — PHYSICAL MEDIA RUNTIME CERTIFICATION'
Add-Line ("STARTED_AT={0}" -f (Get-Date).ToString('o'))
Add-Line ("OUTPUT_DIR={0}" -f $OutputDir)
Add-Line ("DURATION_SECONDS={0}" -f $DurationSeconds)
Add-Line 'MUTATION_SCOPE=TEMP_SYNTHETIC_ARTIFACTS_ONLY'
Add-Line 'AUTO_PUBLICATION=FALSE'

$Ffmpeg = Get-Application 'ffmpeg.exe'
if ($null -eq $Ffmpeg) { $Ffmpeg = Get-Application 'ffmpeg' }
$Ffprobe = Get-Application 'ffprobe.exe'
if ($null -eq $Ffprobe) { $Ffprobe = Get-Application 'ffprobe' }
$NvidiaSmi = Get-Application 'nvidia-smi.exe'
if ($null -eq $NvidiaSmi) { $NvidiaSmi = Get-Application 'nvidia-smi' }

if ($null -eq $Ffmpeg) { Add-Blocker 'FFMPEG_MISSING' 'FFmpeg is not available on PATH.' }
if ($null -eq $Ffprobe) { Add-Blocker 'FFPROBE_MISSING' 'FFprobe is not available on PATH.' }
if ($null -eq $NvidiaSmi) { Add-Blocker 'NVIDIA_SMI_MISSING' 'nvidia-smi is not available on PATH.' }

if ($null -ne $NvidiaSmi) {
    $Gpu = Invoke-Native $NvidiaSmi.Source @(
        '--query-gpu=name,driver_version,memory.total,memory.free',
        '--format=csv,noheader'
    )
    Add-NativeResult 'NVIDIA_SMI_GPU' $Gpu
    if (-not $Gpu.Success) { Add-Blocker 'NVIDIA_SMI_FAILED' 'GPU query failed.' }
}

if ($null -ne $Ffmpeg) {
    $Version = Invoke-Native $Ffmpeg.Source @('-version')
    Add-NativeResult 'FFMPEG_VERSION' $Version
    $Encoders = Invoke-Native $Ffmpeg.Source @('-hide_banner', '-encoders')
    Add-Line ("H264_NVENC_LISTED={0}" -f (Bool-Text ($Encoders.Stdout -match 'h264_nvenc')))
    Add-Line ("LIBX264_LISTED={0}" -f (Bool-Text ($Encoders.Stdout -match 'libx264')))
}

$NvencResult = $null
$X264Result = $null
if ($null -ne $Ffmpeg -and $null -ne $Ffprobe) {
    $NvencResult = Invoke-EncodeProbe \
        -Label 'NVENC' -Codec 'h264_nvenc' \
        -FfmpegPath $Ffmpeg.Source -FfprobePath $Ffprobe.Source \
        -OutputFile $NvencFile -Duration $DurationSeconds
    if (-not $NvencResult.Success -or -not $NvencResult.ProbeSuccess) {
        Add-Blocker 'NVENC_REAL_ENCODE_FAILED' 'Real synthetic h264_nvenc encode/probe did not complete successfully.'
    }

    $X264Result = Invoke-EncodeProbe \
        -Label 'LIBX264' -Codec 'libx264' \
        -FfmpegPath $Ffmpeg.Source -FfprobePath $Ffprobe.Source \
        -OutputFile $X264File -Duration $DurationSeconds
    if (-not $X264Result.Success -or -not $X264Result.ProbeSuccess) {
        Add-Blocker 'LIBX264_REAL_ENCODE_FAILED' 'Real synthetic libx264 encode/probe did not complete successfully.'
    }
}

Add-Line ("PHYSICAL_NVENC_PROVEN={0}" -f (Bool-Text (
    $null -ne $NvencResult -and $NvencResult.Success -and $NvencResult.ProbeSuccess
)))
Add-Line ("LIBX264_FALLBACK_PROVEN={0}" -f (Bool-Text (
    $null -ne $X264Result -and $X264Result.Success -and $X264Result.ProbeSuccess
)))
Add-Line 'CUDA_DEPENDENCY_RUNTIME_PROVEN=FALSE'
Add-Line 'CUDA_DEPENDENCY_NOTE=nvidia-smi/NVENC do not prove CUDA use by Python or AI dependencies.'
Add-Line ("BLOCKER_COUNT={0}" -f $script:Blockers.Count)
Add-Line ("WARNING_COUNT={0}" -f $script:Warnings.Count)
$GatePass = ($script:Blockers.Count -eq 0)
Add-Line ("RUNTIME_MEDIA_GATE_PASS={0}" -f (Bool-Text $GatePass))
Add-Line ("FINISHED_AT={0}" -f (Get-Date).ToString('o'))

$script:Lines | Set-Content -LiteralPath $ReportPath -Encoding UTF8
$ReportHash = Get-Sha256Hex $ReportPath
("{0}  {1}" -f $ReportHash, [System.IO.Path]::GetFileName($ReportPath)) |
    Set-Content -LiteralPath $HashPath -Encoding ASCII

Write-Output ("RUNTIME_MEDIA_GATE_PASS={0}" -f (Bool-Text $GatePass))
Write-Output ("RUNTIME_MEDIA_BLOCKER_COUNT={0}" -f $script:Blockers.Count)
Write-Output ("RUNTIME_MEDIA_WARNING_COUNT={0}" -f $script:Warnings.Count)
Write-Output ("RUNTIME_MEDIA_REPORT={0}" -f $ReportPath)
Write-Output ("RUNTIME_MEDIA_SHA256={0}" -f $ReportHash)
Write-Output ("RUNTIME_MEDIA_HASH_FILE={0}" -f $HashPath)

if ($GatePass) { exit 0 }
exit 2
