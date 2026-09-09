#Requires -Version 5.1
<##
.SYNOPSIS
  Non-destructive physical media runtime certification for El Centinela.
.DESCRIPTION
  Run only after the read-only PC preflight has been reviewed and the repo safely
  reconciled. Writes synthetic video evidence only below %TEMP% (or -OutputRoot).
  No installs, downloads, Git mutation, project-media writes, or publication.
##>
[CmdletBinding()]
param([string]$OutputRoot=$env:TEMP,[ValidateRange(1,10)][int]$DurationSeconds=2)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$script:Lines=@(); $script:Blockers=@()
function Add-Line { param([AllowEmptyString()][string]$Text='') $script:Lines += $Text }
function Add-Blocker { param([string]$Code,[string]$Message) $script:Blockers += $Code; Add-Line ("[BLOCKER] $Code | $Message") }
function Bool-Text { param([bool]$Value) if($Value){'TRUE'}else{'FALSE'} }
function Get-App { param([string]$Name) Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1 }
function Quote-Arg { param([string]$Value) if($Value -notmatch '[\s"]'){return $Value}; if($Value.Contains('"')){throw 'Quote in argument'}; return '"'+$Value+'"' }
function Invoke-Native {
  param([string]$Executable,[string[]]$Arguments=@())
  $i=New-Object System.Diagnostics.ProcessStartInfo; $i.FileName=$Executable; $i.UseShellExecute=$false; $i.RedirectStandardOutput=$true; $i.RedirectStandardError=$true; $i.CreateNoWindow=$true
  $i.Arguments=(($Arguments|ForEach-Object{Quote-Arg ([string]$_)}) -join ' ')
  $p=New-Object System.Diagnostics.Process; $p.StartInfo=$i
  try{[void]$p.Start();$o=$p.StandardOutput.ReadToEndAsync();$e=$p.StandardError.ReadToEndAsync();$p.WaitForExit();[pscustomobject]@{ExitCode=[int]$p.ExitCode;Stdout=$o.GetAwaiter().GetResult().TrimEnd();Stderr=$e.GetAwaiter().GetResult().TrimEnd();Success=($p.ExitCode -eq 0)}}finally{$p.Dispose()}
}
function Add-Result { param([string]$Name,[psobject]$Result) Add-Line "--- $Name ---"; Add-Line ("EXIT_CODE={0}" -f $Result.ExitCode); Add-Line ("SUCCESS={0}" -f (Bool-Text $Result.Success)); if($Result.Stdout){Add-Line $Result.Stdout}; if($Result.Stderr){Add-Line $Result.Stderr} }
function Hash-File { param([string]$Path) (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant() }
function Invoke-EncodeProbe {
  param([string]$Label,[string]$Codec,[string]$Ffmpeg,[string]$Ffprobe,[string]$Output,[int]$Duration)
  $enc=Invoke-Native $Ffmpeg @('-hide_banner','-y','-f','lavfi','-i','testsrc2=size=1080x1920:rate=30','-t',[string]$Duration,'-an','-c:v',$Codec,'-pix_fmt','yuv420p',$Output); Add-Result "ENCODE_$Label" $enc
  if(-not $enc.Success){return [pscustomobject]@{Success=$false;Probe=$false}}
  if(-not (Test-Path -LiteralPath $Output -PathType Leaf)){Add-Blocker "${Label}_OUTPUT_MISSING" 'Output missing';return [pscustomobject]@{Success=$false;Probe=$false}}
  $item=Get-Item -LiteralPath $Output; if($item.Length -le 0){Add-Blocker "${Label}_OUTPUT_EMPTY" 'Output empty';return [pscustomobject]@{Success=$false;Probe=$false}}
  $probe=Invoke-Native $Ffprobe @('-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,r_frame_rate,pix_fmt','-show_entries','format=duration,size','-of','json',$Output); Add-Result "PROBE_$Label" $probe
  Add-Line ("${Label}_BYTES={0}" -f $item.Length); Add-Line ("${Label}_SHA256={0}" -f (Hash-File $Output)); [pscustomobject]@{Success=$true;Probe=$probe.Success}
}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'; $dir=Join-Path $OutputRoot "centinela-runtime-media-cert-$stamp"; New-Item -ItemType Directory -Path $dir -Force|Out-Null
$report=Join-Path $dir 'runtime-media-certification.txt'; $hashFile=Join-Path $dir 'runtime-media-certification.sha256.txt'; $nvFile=Join-Path $dir 'nvenc.mp4'; $xFile=Join-Path $dir 'x264.mp4'
Add-Line 'EL CENTINELA DEL UNIVERSO — PHYSICAL MEDIA RUNTIME CERTIFICATION'; Add-Line ("STARTED_AT={0}" -f (Get-Date).ToString('o')); Add-Line "OUTPUT_DIR=$dir"; Add-Line 'MUTATION_SCOPE=TEMP_SYNTHETIC_ARTIFACTS_ONLY'; Add-Line 'AUTO_PUBLICATION=FALSE'
$ff=Get-App 'ffmpeg.exe';if($null -eq $ff){$ff=Get-App 'ffmpeg'};$fp=Get-App 'ffprobe.exe';if($null -eq $fp){$fp=Get-App 'ffprobe'};$ns=Get-App 'nvidia-smi.exe';if($null -eq $ns){$ns=Get-App 'nvidia-smi'}
if($null -eq $ff){Add-Blocker 'FFMPEG_MISSING' 'FFmpeg not on PATH'};if($null -eq $fp){Add-Blocker 'FFPROBE_MISSING' 'FFprobe not on PATH'};if($null -eq $ns){Add-Blocker 'NVIDIA_SMI_MISSING' 'nvidia-smi not on PATH'}
if($null -ne $ns){$g=Invoke-Native $ns.Source @('--query-gpu=name,driver_version,memory.total,memory.free','--format=csv,noheader');Add-Result 'NVIDIA_SMI_GPU' $g;if(-not $g.Success){Add-Blocker 'NVIDIA_SMI_FAILED' 'GPU query failed'}}
$nv=$null;$x=$null
if($null -ne $ff -and $null -ne $fp){$v=Invoke-Native $ff.Source @('-version');Add-Result 'FFMPEG_VERSION' $v;$encs=Invoke-Native $ff.Source @('-hide_banner','-encoders');Add-Line ("H264_NVENC_LISTED={0}" -f (Bool-Text ($encs.Stdout -match 'h264_nvenc')));Add-Line ("LIBX264_LISTED={0}" -f (Bool-Text ($encs.Stdout -match 'libx264')));$nv=Invoke-EncodeProbe -Label 'NVENC' -Codec 'h264_nvenc' -Ffmpeg $ff.Source -Ffprobe $fp.Source -Output $nvFile -Duration $DurationSeconds;if(-not $nv.Success -or -not $nv.Probe){Add-Blocker 'NVENC_REAL_ENCODE_FAILED' 'Synthetic NVENC encode/probe failed'};$x=Invoke-EncodeProbe -Label 'LIBX264' -Codec 'libx264' -Ffmpeg $ff.Source -Ffprobe $fp.Source -Output $xFile -Duration $DurationSeconds;if(-not $x.Success -or -not $x.Probe){Add-Blocker 'LIBX264_REAL_ENCODE_FAILED' 'Synthetic libx264 encode/probe failed'}}
$nvPass=$null -ne $nv -and $nv.Success -and $nv.Probe;$xPass=$null -ne $x -and $x.Success -and $x.Probe;Add-Line ("PHYSICAL_NVENC_PROVEN={0}" -f (Bool-Text $nvPass));Add-Line ("LIBX264_FALLBACK_PROVEN={0}" -f (Bool-Text $xPass));Add-Line 'CUDA_DEPENDENCY_RUNTIME_PROVEN=FALSE';Add-Line 'CUDA_DEPENDENCY_NOTE=NVENC/nvidia-smi do not prove CUDA use by Python or AI dependencies.'
$pass=$script:Blockers.Count -eq 0;Add-Line ("BLOCKER_COUNT={0}" -f $script:Blockers.Count);Add-Line ("RUNTIME_MEDIA_GATE_PASS={0}" -f (Bool-Text $pass));Add-Line ("FINISHED_AT={0}" -f (Get-Date).ToString('o'))
$script:Lines|Set-Content -LiteralPath $report -Encoding UTF8;$rh=Hash-File $report;("$rh  "+[System.IO.Path]::GetFileName($report))|Set-Content -LiteralPath $hashFile -Encoding ASCII
Write-Output ("RUNTIME_MEDIA_GATE_PASS={0}" -f (Bool-Text $pass));Write-Output ("RUNTIME_MEDIA_BLOCKER_COUNT={0}" -f $script:Blockers.Count);Write-Output "RUNTIME_MEDIA_REPORT=$report";Write-Output "RUNTIME_MEDIA_SHA256=$rh";Write-Output "RUNTIME_MEDIA_HASH_FILE=$hashFile";if($pass){exit 0};exit 2
