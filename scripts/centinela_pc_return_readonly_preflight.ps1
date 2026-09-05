#Requires -Version 5.1
<##
.SYNOPSIS
    Read-only evidence collector for the EL CENTINELA DEL UNIVERSO PC return.

.DESCRIPTION
    Collects Git, Windows, storage, NVIDIA/CUDA, FFmpeg, Python/uv and Ollama
    evidence without changing the repository, installing packages, starting
    services, pulling/rebasing/merging, modifying drivers, or deleting files.

    Output is written under %TEMP% (or -OutputRoot), never inside the repository.
    PREFLIGHT_COMPLETE is a deprecated alias of PREFLIGHT_GATE_COMPLETE.
##>

[CmdletBinding()]
param(
    [string]$RepoPath = 'E:\Github\MoneyPrinterTurbo',
    [string]$OutputRoot = $env:TEMP
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ExpectedBranch = 'centinela-cert/golden-real-e2e-v0.1'
$ExpectedHead = '186104539a7116ad48b96beac90eccd3c4c37801'
$ExpectedStashSha = '22ee99b0703be803e63beaed2370485c84604c9a'
$ExpectedStashLabel = 'C2.11O-M V34 pre-V33 preserve 20260826-172847'
$KnownUntracked = @(
    'app/services/centinela/quality/f57_real_runner.py',
    'test/services/test_f57_real_runner.py',
    'test/services/test_public_source_rights.py'
)

$script:ReportLines = @()
$script:Blockers = @()
$script:Warnings = @()
$script:CollectorFailed = $false

$PreflightExecutionStarted = $true
$PreflightExecutionFinished = $false
$PreflightCollectorStatus = 'FAILED'
$PreflightReportWritten = $false
$PreflightReportHashed = $false
$PreflightHashFileWritten = $false
$PreflightGateComplete = $false
$ExitCode = 3
$ReportHash = ''
$OutputDir = ''
$ReportPath = ''
$HashPath = ''

$RepositoryFound = $false
$RepositoryAccessible = $false
$GitAvailable = $false
$RepositoryIsGitWorktree = $false
$HeadReadable = $false
$HeadSha = ''
$BranchReadable = $false
$HeadMode = 'UNKNOWN'
$BranchName = ''
$StatusReadable = $false
$StashInventoryComplete = $false
$CriticalFileInventoryComplete = $false
$GitEvidenceComplete = $false

function Bool-Text {
    param([bool]$Value)
    if ($Value) { return 'TRUE' }
    return 'FALSE'
}

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

function Add-Blocker {
    param(
        [string]$Code,
        [string]$Message
    )
    $script:Blockers += $Code
    Add-Line ("[BLOCKER] {0} | {1}" -f $Code, $Message)
}

function Add-Warning {
    param(
        [string]$Code,
        [string]$Message
    )
    $script:Warnings += $Code
    Add-Line ("[WARNING] {0} | {1}" -f $Code, $Message)
}

function Add-Fatal {
    param(
        [string]$Code,
        [string]$Message
    )
    $script:CollectorFailed = $true
    Add-Blocker $Code $Message
}

function Command-Application {
    param([string]$Name)
    return Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Get-Sha256Hex {
    param([string]$LiteralPath)

    $Stream = $null
    $Hasher = $null
    try {
        $Stream = [System.IO.File]::Open(
            $LiteralPath,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::Read
        )
        $Hasher = [System.Security.Cryptography.SHA256]::Create()
        $Digest = $Hasher.ComputeHash($Stream)
        return ([System.BitConverter]::ToString($Digest)).Replace('-', '')
    }
    finally {
        if ($null -ne $Hasher) {
            $Hasher.Dispose()
        }
        if ($null -ne $Stream) {
            $Stream.Dispose()
        }
    }
}

function ConvertTo-NativeArgument {
    param([AllowEmptyString()][string]$Value)
    if ([string]::IsNullOrEmpty($Value)) {
        return '""'
    }
    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    if ($Value.Contains('"')) {
        throw 'Native argument contains an unsupported quote character.'
    }
    $Escaped = $Value -replace '(\\+)$', '${1}${1}'
    return '"' + $Escaped + '"'
}

function Invoke-NativeCommand {
    param(
        [string]$Executable,
        [string[]]$Arguments = @()
    )

    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $Executable
    $StartInfo.UseShellExecute = $false
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $StartInfo.CreateNoWindow = $true
    $StartInfo.Arguments = (($Arguments | ForEach-Object {
        ConvertTo-NativeArgument ([string]$_)
    }) -join ' ')

    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $StartInfo

    try {
        [void]$Process.Start()
        $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
        $StderrTask = $Process.StandardError.ReadToEndAsync()
        $Process.WaitForExit()
        $Stdout = $StdoutTask.GetAwaiter().GetResult()
        $Stderr = $StderrTask.GetAwaiter().GetResult()
        return [pscustomobject]@{
            ExitCode = [int]$Process.ExitCode
            Stdout = $Stdout.TrimEnd()
            Stderr = $Stderr.TrimEnd()
            Success = ($Process.ExitCode -eq 0)
            Exception = ''
        }
    }
    catch {
        return [pscustomobject]@{
            ExitCode = -1
            Stdout = ''
            Stderr = ''
            Success = $false
            Exception = $_.Exception.Message
        }
    }
    finally {
        $Process.Dispose()
    }
}

function Add-NativeResult {
    param(
        [string]$Name,
        [psobject]$Result
    )

    Add-Line "--- $Name ---"
    Add-Line ("EXIT_CODE={0}" -f $Result.ExitCode)
    Add-Line ("SUCCESS={0}" -f (Bool-Text $Result.Success))
    Add-Line 'STDOUT:'
    if ([string]::IsNullOrWhiteSpace($Result.Stdout)) {
        Add-Line '[NO OUTPUT]'
    }
    else {
        Add-Line $Result.Stdout
    }
    Add-Line 'STDERR:'
    if ([string]::IsNullOrWhiteSpace($Result.Stderr)) {
        Add-Line '[NO OUTPUT]'
    }
    else {
        Add-Line $Result.Stderr
    }
    if (-not [string]::IsNullOrWhiteSpace($Result.Exception)) {
        Add-Line ("EXCEPTION={0}" -f $Result.Exception)
    }
    Add-Line ''
}

function Invoke-OptionalNativeCapture {
    param(
        [string]$Name,
        [string]$Executable,
        [string[]]$Arguments,
        [string]$WarningCode
    )

    $Result = Invoke-NativeCommand $Executable $Arguments
    Add-NativeResult $Name $Result
    if (-not $Result.Success) {
        Add-Warning $WarningCode ("{0} failed with exit code {1}." -f $Name, $Result.ExitCode)
    }
    return $Result
}

function Invoke-PowerShellCapture {
    param(
        [string]$Name,
        [scriptblock]$Action,
        [string]$WarningCode
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
        Add-Warning $WarningCode ("{0}: {1}" -f $Name, $_.Exception.Message)
    }
    Add-Line ''
}

function Invoke-GitProbe {
    param(
        [string]$GitExecutable,
        [string[]]$Arguments
    )
    $GitArguments = @('--no-optional-locks', '-C', $RepoPath) + $Arguments
    return Invoke-NativeCommand $GitExecutable $GitArguments
}

function Write-TerminalState {
    Write-Host 'PREFLIGHT_SCHEMA_VERSION=2'
    Write-Host ("PREFLIGHT_EXECUTION_STARTED={0}" -f (Bool-Text $PreflightExecutionStarted))
    Write-Host ("PREFLIGHT_EXECUTION_FINISHED={0}" -f (Bool-Text $PreflightExecutionFinished))
    Write-Host ("PREFLIGHT_COLLECTOR_STATUS={0}" -f $PreflightCollectorStatus)
    Write-Host ("PREFLIGHT_REPORT_WRITTEN={0}" -f (Bool-Text $PreflightReportWritten))
    Write-Host ("PREFLIGHT_REPORT_HASHED={0}" -f (Bool-Text $PreflightReportHashed))
    Write-Host ("PREFLIGHT_HASH_FILE_WRITTEN={0}" -f (Bool-Text $PreflightHashFileWritten))
    Write-Host ("PREFLIGHT_BLOCKER_COUNT={0}" -f $script:Blockers.Count)
    Write-Host ("PREFLIGHT_WARNING_COUNT={0}" -f $script:Warnings.Count)
    Write-Host ("PREFLIGHT_BLOCKERS={0}" -f ($script:Blockers -join ';'))
    Write-Host ("PREFLIGHT_WARNINGS={0}" -f ($script:Warnings -join ';'))
    Write-Host ("REPOSITORY_FOUND={0}" -f (Bool-Text $RepositoryFound))
    Write-Host ("REPOSITORY_ACCESSIBLE={0}" -f (Bool-Text $RepositoryAccessible))
    Write-Host ("GIT_AVAILABLE={0}" -f (Bool-Text $GitAvailable))
    Write-Host ("REPOSITORY_IS_GIT_WORKTREE={0}" -f (Bool-Text $RepositoryIsGitWorktree))
    Write-Host ("HEAD_READABLE={0}" -f (Bool-Text $HeadReadable))
    Write-Host ("BRANCH_READABLE={0}" -f (Bool-Text $BranchReadable))
    Write-Host ("HEAD_MODE={0}" -f $HeadMode)
    Write-Host ("STATUS_READABLE={0}" -f (Bool-Text $StatusReadable))
    Write-Host ("STASH_INVENTORY_COMPLETE={0}" -f (Bool-Text $StashInventoryComplete))
    Write-Host ("CRITICAL_FILE_INVENTORY_COMPLETE={0}" -f (Bool-Text $CriticalFileInventoryComplete))
    Write-Host ("GIT_EVIDENCE_COMPLETE={0}" -f (Bool-Text $GitEvidenceComplete))
    Write-Host ("PREFLIGHT_GATE_COMPLETE={0}" -f (Bool-Text $PreflightGateComplete))
    Write-Host ("PREFLIGHT_COMPLETE={0}" -f (Bool-Text $PreflightGateComplete))
    Write-Host 'PREFLIGHT_COMPLETE_SEMANTICS=ALIAS_OF_PREFLIGHT_GATE_COMPLETE'
    if (-not [string]::IsNullOrWhiteSpace($ReportPath)) {
        Write-Host ("PREFLIGHT_REPORT={0}" -f $ReportPath)
    }
    if (-not [string]::IsNullOrWhiteSpace($ReportHash)) {
        Write-Host ("PREFLIGHT_SHA256={0}" -f $ReportHash)
    }
    if (-not [string]::IsNullOrWhiteSpace($HashPath)) {
        Write-Host ("PREFLIGHT_HASH_FILE={0}" -f $HashPath)
    }
    Write-Host ("EXIT_CODE={0}" -f $ExitCode)
}

# Create a unique evidence directory. Never reuse an existing evidence directory.
try {
    if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
        throw 'OutputRoot is empty.'
    }
    $OutputRootFull = [System.IO.Path]::GetFullPath($OutputRoot).TrimEnd(
        [char[]]@('\', '/')
    )
    $RepoPathFull = [System.IO.Path]::GetFullPath($RepoPath).TrimEnd(
        [char[]]@('\', '/')
    )
    $RepoPrefix = $RepoPathFull + [System.IO.Path]::DirectorySeparatorChar
    if (
        $OutputRootFull.Equals(
            $RepoPathFull,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or
        $OutputRootFull.StartsWith(
            $RepoPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw 'OutputRoot must not be the repository or a child of it.'
    }
    $Stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $RunId = [Guid]::NewGuid().ToString('N').Substring(0, 12)
    $OutputDir = Join-Path $OutputRoot ("Centinela_Preflight_{0}_{1}" -f $Stamp, $RunId)
    $ReportPath = Join-Path $OutputDir 'centinela-pc-return-preflight.txt'
    $HashPath = Join-Path $OutputDir 'centinela-pc-return-preflight.sha256.txt'
    New-Item -ItemType Directory -Path $OutputDir -ErrorAction Stop | Out-Null
}
catch {
    Add-Fatal 'B_REPORT_DIRECTORY_CREATE_FAILED' $_.Exception.Message
    $PreflightExecutionFinished = $true
    $PreflightCollectorStatus = 'FAILED'
    $ExitCode = 3
    Write-TerminalState
    exit $ExitCode
}

try {
    Add-Line 'EL CENTINELA DEL UNIVERSO - PC RETURN READ-ONLY PREFLIGHT'
    Add-Line ("Generated: {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss K'))
    Add-Line ("Computer: {0}" -f $env:COMPUTERNAME)
    Add-Line ("User: {0}" -f $env:USERNAME)
    Add-Line ("RepoPath requested: {0}" -f $RepoPath)
    Add-Line 'PREFLIGHT_SCHEMA_VERSION=2'
    Add-Line 'PREFLIGHT_EXECUTION_STARTED=TRUE'
    Add-Line 'MODE=READ_ONLY_EVIDENCE_COLLECTION'
    Add-Line 'NO_PULL=TRUE'
    Add-Line 'NO_MERGE=TRUE'
    Add-Line 'NO_REBASE=TRUE'
    Add-Line 'NO_RESET=TRUE'
    Add-Line 'NO_CLEAN=TRUE'
    Add-Line 'NO_STASH_RESTORE=TRUE'
    Add-Line 'NO_BRANCH_SWITCH=TRUE'
    Add-Line 'NO_FILE_DELETION=TRUE'
    Add-Line 'NO_INSTALL=TRUE'
    Add-Line 'NO_DRIVER_CHANGE=TRUE'
    Add-Line 'NO_MODEL_DOWNLOAD=TRUE'

    Add-Section '1. WINDOWS / CPU / RAM'
    Invoke-PowerShellCapture 'Windows OS' {
        Get-CimInstance Win32_OperatingSystem -ErrorAction Stop |
            Select-Object Caption, Version, BuildNumber, OSArchitecture,
                @{Name='TotalRAM_GiB';Expression={[math]::Round($_.TotalVisibleMemorySize / 1MB, 2)}},
                @{Name='FreeRAM_GiB';Expression={[math]::Round($_.FreePhysicalMemory / 1MB, 2)}} |
            Format-List
    } 'W_WINDOWS_PROBE_FAILED'
    Invoke-PowerShellCapture 'CPU' {
        Get-CimInstance Win32_Processor -ErrorAction Stop |
            Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed |
            Format-List
    } 'W_WINDOWS_PROBE_FAILED'
    Invoke-PowerShellCapture 'Video controllers' {
        Get-CimInstance Win32_VideoController -ErrorAction Stop |
            Select-Object Name, DriverVersion,
                @{Name='AdapterRAM_GiB';Expression={
                    if ($_.AdapterRAM) {[math]::Round($_.AdapterRAM / 1GB, 2)} else {$null}
                }} |
            Format-Table -AutoSize
    } 'W_WINDOWS_PROBE_FAILED'

    Add-Section '2. STORAGE / CANONICAL PATHS'
    foreach ($DriveLetter in @('D', 'E')) {
        Invoke-PowerShellCapture "Drive $DriveLetter volume" {
            Get-Volume -DriveLetter $DriveLetter -ErrorAction Stop |
                Select-Object DriveLetter, FileSystemLabel, FileSystem, HealthStatus,
                    @{Name='Size_GiB';Expression={[math]::Round($_.Size / 1GB, 2)}},
                    @{Name='Free_GiB';Expression={[math]::Round($_.SizeRemaining / 1GB, 2)}} |
                Format-List
        } 'W_STORAGE_PROBE_FAILED'
        Invoke-PowerShellCapture "Drive $DriveLetter physical disk" {
            Get-Partition -DriveLetter $DriveLetter -ErrorAction Stop |
                Get-Disk -ErrorAction Stop |
                Select-Object Number, FriendlyName, BusType, MediaType,
                    @{Name='Size_GiB';Expression={[math]::Round($_.Size / 1GB, 2)}} |
                Format-List
        } 'W_STORAGE_PROBE_FAILED'
    }

    $CanonicalPaths = @(
        'E:\Github\MoneyPrinterTurbo',
        'E:\IA\AstroMedia',
        'E:\IA\Qwen3-TTS',
        'D:\ASTRONOMÍA\Medios',
        'D:\ASTRONOMÍA\Medios\R9_Golden_Local'
    )
    foreach ($Path in $CanonicalPaths) {
        try {
            Add-Line ("PATH_EXISTS | {0} | {1}" -f (Test-Path -LiteralPath $Path -ErrorAction Stop), $Path)
        }
        catch {
            Add-Line ("PATH_PROBE_ERROR | {0} | {1}" -f $_.Exception.Message, $Path)
            Add-Warning 'W_CANONICAL_COMPONENT_PROBE_FAILED' $Path
        }
    }

    Add-Section '3. GIT - PRESERVE BEFORE RECONCILIATION'

    $RepoPathProbeFailed = $false
    try {
        $RepositoryFound = Test-Path -LiteralPath $RepoPath -ErrorAction Stop
    }
    catch {
        $RepoPathProbeFailed = $true
        Add-Blocker 'B_REPO_PATH_INACCESSIBLE' $_.Exception.Message
    }

    if (-not $RepoPathProbeFailed -and -not $RepositoryFound) {
        Add-Blocker 'B_REPO_PATH_MISSING' ("Repository path not found: {0}" -f $RepoPath)
    }
    elseif ($RepositoryFound) {
        try {
            $RepoItem = Get-Item -LiteralPath $RepoPath -ErrorAction Stop
            if (-not $RepoItem.PSIsContainer) {
                Add-Blocker 'B_REPO_PATH_INACCESSIBLE' ("Repository path is not a directory: {0}" -f $RepoPath)
            }
            else {
                $RepositoryAccessible = $true
            }
        }
        catch {
            Add-Blocker 'B_REPO_PATH_INACCESSIBLE' $_.Exception.Message
        }
    }

    $GitCommand = Command-Application 'git'
    if ($null -eq $GitCommand) {
        Add-Blocker 'B_GIT_UNAVAILABLE' 'git application is not available in PATH.'
    }
    else {
        $GitAvailable = $true
        $GitExecutable = $GitCommand.Source
        Add-Line ("GIT_EXECUTABLE={0}" -f $GitExecutable)
    }

    if ($RepositoryAccessible -and $GitAvailable) {
        $WorktreeResult = Invoke-GitProbe $GitExecutable @('rev-parse', '--is-inside-work-tree')
        Add-NativeResult 'git rev-parse --is-inside-work-tree' $WorktreeResult
        if ($WorktreeResult.Success -and $WorktreeResult.Stdout.Trim() -eq 'true') {
            $RepositoryIsGitWorktree = $true
        }
        else {
            Add-Blocker 'B_NOT_GIT_WORKTREE' 'Repository path is not a readable Git worktree.'
        }
    }

    if ($RepositoryIsGitWorktree) {
        $RootResult = Invoke-GitProbe $GitExecutable @('rev-parse', '--show-toplevel')
        Add-NativeResult 'git rev-parse --show-toplevel' $RootResult
        if (-not $RootResult.Success) {
            Add-Blocker 'B_CORE_GIT_COMMAND_FAILED' 'Unable to read Git top-level path.'
        }
        else {
            Add-Line ("GIT_ROOT={0}" -f $RootResult.Stdout.Trim())
        }

        $HeadResult = Invoke-GitProbe $GitExecutable @('rev-parse', 'HEAD')
        Add-NativeResult 'git rev-parse HEAD' $HeadResult
        if ($HeadResult.Success -and $HeadResult.Stdout.Trim() -match '^[0-9a-fA-F]{40}$') {
            $HeadReadable = $true
            $HeadSha = $HeadResult.Stdout.Trim()
        }
        else {
            Add-Blocker 'B_HEAD_UNREADABLE' 'Unable to read a 40-character Git HEAD SHA.'
        }

        $BranchResult = Invoke-GitProbe $GitExecutable @('branch', '--show-current')
        Add-NativeResult 'git branch --show-current' $BranchResult
        if ($BranchResult.Success) {
            $BranchReadable = $true
            $BranchName = $BranchResult.Stdout.Trim()
            if ([string]::IsNullOrWhiteSpace($BranchName)) {
                $HeadMode = 'DETACHED'
                Add-Warning 'W_DETACHED_HEAD_OBSERVED' 'HEAD is detached; this is valid observed state.'
            }
            else {
                $HeadMode = 'BRANCH'
            }
        }
        else {
            Add-Blocker 'B_BRANCH_QUERY_FAILED' 'Unable to determine branch/detached state.'
        }

        Add-Line ("GIT_HEAD={0}" -f $HeadSha)
        Add-Line ("GIT_BRANCH={0}" -f $BranchName)
        Add-Line ("HEAD_MODE={0}" -f $HeadMode)
        Add-Line ("EXPECTED_BRANCH={0}" -f $ExpectedBranch)
        Add-Line ("EXPECTED_HEAD={0}" -f $ExpectedHead)

        if ($HeadReadable) {
            $HeadMatch = ($HeadSha -eq $ExpectedHead)
            Add-Line ("HEAD_MATCH={0}" -f (Bool-Text $HeadMatch))
            if (-not $HeadMatch) {
                Add-Warning 'W_HISTORICAL_HEAD_MISMATCH' 'Observed HEAD differs from historical local expectation.'
            }
        }
        else {
            Add-Line 'HEAD_MATCH=UNKNOWN'
        }

        if ($BranchReadable -and $HeadMode -eq 'BRANCH') {
            $BranchMatch = ($BranchName -eq $ExpectedBranch)
            Add-Line ("BRANCH_MATCH={0}" -f (Bool-Text $BranchMatch))
            if (-not $BranchMatch) {
                Add-Warning 'W_HISTORICAL_BRANCH_MISMATCH' 'Observed branch differs from historical local expectation.'
            }
        }
        elseif ($BranchReadable) {
            Add-Line 'BRANCH_MATCH=NOT_APPLICABLE_DETACHED'
        }
        else {
            Add-Line 'BRANCH_MATCH=UNKNOWN'
        }

        $StatusResult = Invoke-GitProbe $GitExecutable @(
            'status', '--porcelain=v1', '--branch', '--untracked-files=all'
        )
        Add-NativeResult 'git status --porcelain=v1 --branch --untracked-files=all' $StatusResult
        if ($StatusResult.Success) {
            $StatusReadable = $true
        }
        else {
            Add-Blocker 'B_STATUS_UNREADABLE' 'Unable to capture Git status.'
        }

        $UnstagedResult = Invoke-GitProbe $GitExecutable @('diff', '--name-status')
        Add-NativeResult 'git diff --name-status (unstaged)' $UnstagedResult
        if (-not $UnstagedResult.Success) {
            Add-Warning 'W_UNSTAGED_DIFF_CAPTURE_FAILED' 'Unable to capture unstaged diff inventory.'
        }

        $StagedResult = Invoke-GitProbe $GitExecutable @('diff', '--cached', '--name-status')
        Add-NativeResult 'git diff --cached --name-status (staged)' $StagedResult
        if (-not $StagedResult.Success) {
            Add-Warning 'W_STAGED_DIFF_CAPTURE_FAILED' 'Unable to capture staged diff inventory.'
        }

        $StashResult = Invoke-GitProbe $GitExecutable @(
            'stash', 'list', '--format=%gd|%H|%gs'
        )
        Add-NativeResult 'git stash list with object IDs' $StashResult
        if ($StashResult.Success) {
            $StashInventoryComplete = $true
            $StashEvidence = $StashResult.Stdout
            Add-Line ("EXPECTED_STASH_SHA={0}" -f $ExpectedStashSha)
            Add-Line ("EXPECTED_STASH_LABEL={0}" -f $ExpectedStashLabel)
            $ExpectedStashShaFound = $StashEvidence -match [regex]::Escape($ExpectedStashSha)
            $ExpectedStashLabelFound = $StashEvidence -match [regex]::Escape($ExpectedStashLabel)
            Add-Line ("EXPECTED_STASH_SHA_FOUND={0}" -f (Bool-Text $ExpectedStashShaFound))
            Add-Line ("EXPECTED_STASH_LABEL_FOUND={0}" -f (Bool-Text $ExpectedStashLabelFound))
            if (-not ($ExpectedStashShaFound -and $ExpectedStashLabelFound)) {
                Add-Warning 'W_HISTORICAL_STASH_NOT_FOUND' 'Historical stash SHA/label was not fully matched.'
            }
        }
        else {
            Add-Blocker 'B_STASH_INVENTORY_FAILED' 'Unable to inventory Git stash state.'
        }

        $CriticalInventoryFailed = $false
        foreach ($RelativePath in $KnownUntracked) {
            $FullPath = Join-Path $RepoPath $RelativePath
            $Exists = $false
            $IsFile = $false
            $SizeBytes = ''
            $LastWriteTimeUtc = ''
            $FileHash = ''

            try {
                $Exists = Test-Path -LiteralPath $FullPath -ErrorAction Stop
                if ($Exists) {
                    $Item = Get-Item -LiteralPath $FullPath -ErrorAction Stop
                    $IsFile = -not $Item.PSIsContainer
                    if ($IsFile) {
                        $SizeBytes = [string]$Item.Length
                        $LastWriteTimeUtc = $Item.LastWriteTimeUtc.ToString('o')
                        $FileHash = Get-Sha256Hex $FullPath
                    }
                }
            }
            catch {
                $CriticalInventoryFailed = $true
                Add-Blocker 'B_CRITICAL_FILE_INVENTORY_FAILED' (
                    "{0}: {1}" -f $RelativePath, $_.Exception.Message
                )
            }

            $PathStatusResult = Invoke-GitProbe $GitExecutable @(
                'status', '--porcelain=v1', '--untracked-files=all', '--', $RelativePath
            )
            Add-NativeResult ("git status critical path: {0}" -f $RelativePath) $PathStatusResult
            if (-not $PathStatusResult.Success) {
                $CriticalInventoryFailed = $true
                Add-Blocker 'B_CRITICAL_FILE_INVENTORY_FAILED' (
                    "{0}: Git status failed." -f $RelativePath
                )
            }

            $TrackedResult = Invoke-GitProbe $GitExecutable @(
                'ls-files', '--', $RelativePath
            )
            Add-NativeResult ("git ls-files critical path: {0}" -f $RelativePath) $TrackedResult
            if (-not $TrackedResult.Success) {
                $CriticalInventoryFailed = $true
                Add-Blocker 'B_CRITICAL_FILE_INVENTORY_FAILED' (
                    "{0}: Git tracking query failed." -f $RelativePath
                )
                $TrackingState = 'UNKNOWN'
            }
            elseif ([string]::IsNullOrWhiteSpace($TrackedResult.Stdout)) {
                $TrackingState = 'UNTRACKED_OR_ABSENT'
            }
            else {
                $TrackingState = 'TRACKED'
            }

            Add-Line (
                "CRITICAL_FILE | PATH={0} | EXISTS={1} | IS_FILE={2} | SIZE_BYTES={3} | LAST_WRITE_TIME_UTC={4} | TRACKING_STATE={5} | GIT_STATUS={6}" -f
                $RelativePath,
                (Bool-Text $Exists),
                (Bool-Text $IsFile),
                $SizeBytes,
                $LastWriteTimeUtc,
                $TrackingState,
                $PathStatusResult.Stdout.Replace("`r", '').Replace("`n", '\n')
            )
            if ($Exists -and $IsFile -and -not [string]::IsNullOrWhiteSpace($FileHash)) {
                Add-Line ("CRITICAL_FILE_SHA256 | {0} | {1}" -f $FileHash, $RelativePath)
            }
        }

        if (-not $CriticalInventoryFailed) {
            $CriticalFileInventoryComplete = $true
        }
    }

    $GitEvidenceComplete = (
        $RepositoryFound -and
        $RepositoryAccessible -and
        $GitAvailable -and
        $RepositoryIsGitWorktree -and
        $HeadReadable -and
        $BranchReadable -and
        $StatusReadable -and
        $StashInventoryComplete -and
        $CriticalFileInventoryComplete
    )

    Add-Section '4. TOOLCHAIN VERSIONS'
    foreach ($Tool in @('git', 'python', 'py', 'uv', 'ffmpeg', 'ffprobe', 'nvidia-smi', 'nvcc', 'ollama')) {
        $Command = Command-Application $Tool
        if ($null -eq $Command) {
            Add-Line ("COMMAND_AVAILABLE | FALSE | {0}" -f $Tool)
        }
        else {
            Add-Line ("COMMAND_AVAILABLE | TRUE | {0} | {1}" -f $Tool, $Command.Source)
        }
    }
    Add-Line ''

    if ($GitAvailable) {
        [void](Invoke-OptionalNativeCapture 'git --version' $GitExecutable @('--version') 'W_OPTIONAL_TOOL_PROBE_FAILED')
    }
    foreach ($ToolProbe in @(
        @('python', '--version'),
        @('py', '-0p'),
        @('uv', '--version'),
        @('nvcc', '--version')
    )) {
        $ToolName = [string]$ToolProbe[0]
        $ToolCommand = Command-Application $ToolName
        if ($null -ne $ToolCommand) {
            [void](Invoke-OptionalNativeCapture (
                "{0} {1}" -f $ToolName, $ToolProbe[1]
            ) $ToolCommand.Source @([string]$ToolProbe[1]) 'W_OPTIONAL_TOOL_PROBE_FAILED')
        }
    }

    Add-Section '5. NVIDIA DRIVER / GPU / CUDA VISIBILITY'
    $NvidiaCommand = Command-Application 'nvidia-smi'
    if ($null -eq $NvidiaCommand) {
        Add-Warning 'W_NVIDIA_SMI_NOT_AVAILABLE' 'nvidia-smi is not available.'
    }
    else {
        [void](Invoke-OptionalNativeCapture 'nvidia-smi summary' $NvidiaCommand.Source @() 'W_NVIDIA_QUERY_FAILED')
        [void](Invoke-OptionalNativeCapture 'nvidia-smi concise GPU query' $NvidiaCommand.Source @(
            '--query-gpu=name,driver_version,memory.total,memory.used,memory.free',
            '--format=csv,noheader,nounits'
        ) 'W_NVIDIA_QUERY_FAILED')
    }
    if ($null -eq (Command-Application 'nvcc')) {
        Add-Warning 'W_NVCC_NOT_AVAILABLE' 'CUDA Toolkit nvcc is not available.'
    }

    Add-Section '6. FFMPEG / NVENC / LIBX264 AVAILABILITY'
    $FfmpegCommand = Command-Application 'ffmpeg'
    if ($null -eq $FfmpegCommand) {
        Add-Warning 'W_FFMPEG_NOT_AVAILABLE' 'ffmpeg is not available.'
    }
    else {
        [void](Invoke-OptionalNativeCapture 'ffmpeg -version' $FfmpegCommand.Source @(
            '-hide_banner', '-version'
        ) 'W_FFMPEG_QUERY_FAILED')
        [void](Invoke-OptionalNativeCapture 'ffmpeg relevant encoders' $FfmpegCommand.Source @(
            '-hide_banner', '-encoders'
        ) 'W_FFMPEG_QUERY_FAILED')
        [void](Invoke-OptionalNativeCapture 'ffmpeg hardware accelerations' $FfmpegCommand.Source @(
            '-hide_banner', '-hwaccels'
        ) 'W_FFMPEG_QUERY_FAILED')
    }

    $FfprobeCommand = Command-Application 'ffprobe'
    if ($null -eq $FfprobeCommand) {
        Add-Warning 'W_FFPROBE_NOT_AVAILABLE' 'ffprobe is not available.'
    }
    else {
        [void](Invoke-OptionalNativeCapture 'ffprobe -version' $FfprobeCommand.Source @(
            '-hide_banner', '-version'
        ) 'W_OPTIONAL_TOOL_PROBE_FAILED')
    }

    Add-Section '7. OLLAMA LOCAL RUNTIME - NO SERVICE START'
    $OllamaCommand = Command-Application 'ollama'
    if ($null -eq $OllamaCommand) {
        Add-Warning 'W_OLLAMA_NOT_AVAILABLE' 'ollama command is not available.'
    }
    else {
        [void](Invoke-OptionalNativeCapture 'ollama --version' $OllamaCommand.Source @(
            '--version'
        ) 'W_OPTIONAL_TOOL_PROBE_FAILED')
    }

    Add-Line '--- Ollama loopback /api/tags (only if already running) ---'
    try {
        $Response = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -Method Get -TimeoutSec 2 -ErrorAction Stop
        Add-Line ($Response | ConvertTo-Json -Depth 8)
    }
    catch {
        Add-Line ("OLLAMA_LOOPBACK_UNAVAILABLE={0}" -f $_.Exception.Message)
        Add-Warning 'W_OLLAMA_LOOPBACK_UNAVAILABLE' 'Ollama loopback endpoint is unavailable.'
    }
    Add-Line ''

    Add-Section '8. CANONICAL LOCAL COMPONENT PATH SNAPSHOT'
    foreach ($Path in @('E:\IA\AstroMedia', 'E:\IA\Qwen3-TTS', 'D:\ASTRONOMÍA\Medios\R9_Golden_Local')) {
        Add-Line "--- $Path ---"
        try {
            $ComponentExists = Test-Path -LiteralPath $Path -PathType Container -ErrorAction Stop
            if ($ComponentExists) {
                Get-ChildItem -LiteralPath $Path -Force -ErrorAction Stop |
                    Select-Object Name, Length, LastWriteTime, Attributes |
                    Format-Table -AutoSize |
                    Out-String -Width 4096 |
                    ForEach-Object { Add-Line $_.TrimEnd() }
            }
            else {
                Add-Line '[NOT FOUND]'
            }
        }
        catch {
            Add-Line ("[ERROR] {0}" -f $_.Exception.Message)
            Add-Warning 'W_CANONICAL_COMPONENT_PROBE_FAILED' (
                "{0}: {1}" -f $Path, $_.Exception.Message
            )
        }
        Add-Line ''
    }

    Add-Section '9. PREFLIGHT INTERPRETATION'
    Add-Line 'This script has not certified CUDA execution, NVENC encoding, Qwen3-TTS quality, Whisper alignment, AstroMedia correctness, F57 local 8/8, Golden E2E, or Publication Package readiness.'
    Add-Line 'It only captures the initial state needed before selective reconciliation and real certification.'
    Add-Line 'COLLECTION_FAILURE_IS_NOT_COLLECTED_NEGATIVE_EVIDENCE=TRUE'
    Add-Line 'PREFLIGHT_COMPLETE_SEMANTICS=DEPRECATED_ALIAS_OF_PREFLIGHT_GATE_COMPLETE'
    Add-Line 'DO_NOT_MERGE_FROM_THIS_REPORT=TRUE'
    Add-Line 'DO_NOT_FREEZE_FROM_THIS_REPORT=TRUE'
    Add-Line 'AUTO_PUBLICATION=FALSE'
}
catch {
    Add-Fatal 'B_UNEXPECTED_EXCEPTION' $_.Exception.Message
}

$PreflightExecutionFinished = $true

if ($script:CollectorFailed) {
    $PreflightCollectorStatus = 'FAILED'
}
elseif (($script:Blockers.Count -gt 0) -or (-not $GitEvidenceComplete)) {
    $PreflightCollectorStatus = 'BLOCKED'
}
else {
    $PreflightCollectorStatus = 'VALID'
}

Add-Section '10. PREFLIGHT COMPLETION STATE'
Add-Line ("REPOSITORY_FOUND={0}" -f (Bool-Text $RepositoryFound))
Add-Line ("REPOSITORY_ACCESSIBLE={0}" -f (Bool-Text $RepositoryAccessible))
Add-Line ("GIT_AVAILABLE={0}" -f (Bool-Text $GitAvailable))
Add-Line ("REPOSITORY_IS_GIT_WORKTREE={0}" -f (Bool-Text $RepositoryIsGitWorktree))
Add-Line ("HEAD_READABLE={0}" -f (Bool-Text $HeadReadable))
Add-Line ("HEAD_SHA={0}" -f $HeadSha)
Add-Line ("BRANCH_READABLE={0}" -f (Bool-Text $BranchReadable))
Add-Line ("HEAD_MODE={0}" -f $HeadMode)
Add-Line ("BRANCH_NAME={0}" -f $BranchName)
Add-Line ("STATUS_READABLE={0}" -f (Bool-Text $StatusReadable))
Add-Line ("STASH_INVENTORY_COMPLETE={0}" -f (Bool-Text $StashInventoryComplete))
Add-Line ("CRITICAL_FILE_INVENTORY_COMPLETE={0}" -f (Bool-Text $CriticalFileInventoryComplete))
Add-Line ("GIT_EVIDENCE_COMPLETE={0}" -f (Bool-Text $GitEvidenceComplete))
Add-Line ("PREFLIGHT_BLOCKER_COUNT={0}" -f $script:Blockers.Count)
Add-Line ("PREFLIGHT_WARNING_COUNT={0}" -f $script:Warnings.Count)
Add-Line ("PREFLIGHT_BLOCKERS={0}" -f ($script:Blockers -join ';'))
Add-Line ("PREFLIGHT_WARNINGS={0}" -f ($script:Warnings -join ';'))
Add-Line ("PREFLIGHT_EXECUTION_FINISHED={0}" -f (Bool-Text $PreflightExecutionFinished))
Add-Line ("PREFLIGHT_COLLECTOR_STATUS={0}" -f $PreflightCollectorStatus)

try {
    $script:ReportLines | Set-Content -LiteralPath $ReportPath -Encoding UTF8 -ErrorAction Stop
    $PreflightReportWritten = $true
}
catch {
    Add-Fatal 'B_REPORT_WRITE_FAILED' $_.Exception.Message
    $PreflightCollectorStatus = 'FAILED'
}

if ($PreflightReportWritten) {
    try {
        $ReportHash = Get-Sha256Hex $ReportPath
        $PreflightReportHashed = $true
    }
    catch {
        Add-Fatal 'B_REPORT_HASH_FAILED' $_.Exception.Message
        $PreflightCollectorStatus = 'FAILED'
    }
}

if ($PreflightReportWritten -and $PreflightReportHashed -and -not $script:CollectorFailed) {
    if (($script:Blockers.Count -eq 0) -and $GitEvidenceComplete) {
        $PreflightCollectorStatus = 'VALID'
        $GateCandidate = $true
        $CandidateExitCode = 0
    }
    else {
        $PreflightCollectorStatus = 'BLOCKED'
        $GateCandidate = $false
        $CandidateExitCode = 2
    }

    $EnvelopeLines = @(
        ("{0}  {1}" -f $ReportHash, (Split-Path $ReportPath -Leaf)),
        '',
        'PREFLIGHT_SCHEMA_VERSION=2',
        'PREFLIGHT_EXECUTION_FINISHED=TRUE',
        ("PREFLIGHT_COLLECTOR_STATUS={0}" -f $PreflightCollectorStatus),
        'PREFLIGHT_REPORT_WRITTEN=TRUE',
        'PREFLIGHT_REPORT_HASHED=TRUE',
        'PREFLIGHT_HASH_FILE_WRITTEN=TRUE',
        ("PREFLIGHT_BLOCKER_COUNT={0}" -f $script:Blockers.Count),
        ("PREFLIGHT_WARNING_COUNT={0}" -f $script:Warnings.Count),
        ("GIT_EVIDENCE_COMPLETE={0}" -f (Bool-Text $GitEvidenceComplete)),
        ("PREFLIGHT_GATE_COMPLETE={0}" -f (Bool-Text $GateCandidate)),
        ("PREFLIGHT_COMPLETE={0}" -f (Bool-Text $GateCandidate)),
        'PREFLIGHT_COMPLETE_SEMANTICS=ALIAS_OF_PREFLIGHT_GATE_COMPLETE',
        ("EXIT_CODE={0}" -f $CandidateExitCode)
    )

    try {
        $EnvelopeLines | Set-Content -LiteralPath $HashPath -Encoding ASCII -ErrorAction Stop
        $ReadBack = Get-Content -LiteralPath $HashPath -Raw -ErrorAction Stop
        foreach ($RequiredLine in $EnvelopeLines) {
            if (-not [string]::IsNullOrWhiteSpace($RequiredLine) -and
                $ReadBack -notmatch [regex]::Escape($RequiredLine)) {
                throw ("Completion envelope verification failed for: {0}" -f $RequiredLine)
            }
        }
        $PreflightHashFileWritten = $true
        $PreflightGateComplete = $GateCandidate
        $ExitCode = $CandidateExitCode
    }
    catch {
        Add-Fatal 'B_HASH_FILE_WRITE_FAILED' $_.Exception.Message
        $PreflightCollectorStatus = 'FAILED'
        $PreflightHashFileWritten = $false
        $PreflightGateComplete = $false
        $ExitCode = 3
    }
}
else {
    $PreflightCollectorStatus = 'FAILED'
    $PreflightGateComplete = $false
    $ExitCode = 3
}

Write-TerminalState
exit $ExitCode
