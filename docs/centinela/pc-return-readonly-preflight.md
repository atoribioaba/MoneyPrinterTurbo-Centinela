# PC return read-only preflight

Prepared: 2026-08-30
Target use: 2026-09-09+

Script:

`scripts/centinela_pc_return_readonly_preflight.ps1`

## Purpose

Reduce the first Windows session to one evidence capture instead of many manual checks. The script is intentionally read-only with respect to the repository and system configuration.

It writes its report only under `%TEMP%` and does **not**:

- pull, fetch, merge, rebase, reset, clean, checkout or stash;
- install/sync Python packages;
- install or start Ollama;
- change CUDA/NVIDIA drivers;
- download models;
- render/encode video;
- delete or alter AstroMedia/media files;
- publish anything.

## Evidence collected

- Windows version/build;
- CPU and RAM;
- video controller metadata;
- D:/E: volumes and physical-disk media/bus type where Windows exposes it;
- existence of canonical MPT/AstroMedia/Qwen/media paths;
- Git branch/HEAD/status/staged/unstaged files;
- stash object IDs/messages;
- SHA-256 for the three known pre-V33 local files if present;
- Git/Python/py/uv versions and locations;
- NVIDIA driver/GPU/VRAM through `nvidia-smi`;
- CUDA Toolkit separately through `nvcc` if installed;
- FFmpeg version, `h264_nvenc`, `hevc_nvenc`, `libx264` and hardware accelerations;
- Ollama version if installed and loopback `/api/tags` only if the service is already running;
- non-recursive directory snapshot of AstroMedia, Qwen3-TTS and owned R9 media folders.

The script explicitly distinguishes discovery from certification: it does not claim real CUDA workload use, successful NVENC encoding, TTS quality or Golden readiness.

## Expected local Git evidence baked into the checker

- branch `centinela-cert/golden-real-e2e-v0.1`;
- HEAD `186104539a7116ad48b96beac90eccd3c4c37801`;
- stash SHA `22ee99b0703be803e63beaed2370485c84604c9a`;
- stash label `C2.11O-M V34 pre-V33 preserve 20260826-172847`;
- known files:
  - `app/services/centinela/quality/f57_real_runner.py`
  - `test/services/test_f57_real_runner.py`
  - `test/services/test_public_source_rights.py`

A mismatch is reported; it is never repaired automatically.

## Safe execution order on PC return

The local working tree must be observed/preserved before reconciliation. If this script is not already present locally, first perform the manual Git identity/status/stash checks, preserve the exact committed and dirty state, then `git fetch` remote refs. After that, obtain/run this script from the remote C3 branch without merging that branch into the local worktree.

Recommended execution once the script exists locally or in a temporary path:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\centinela_pc_return_readonly_preflight.ps1 -RepoPath 'E:\Github\MoneyPrinterTurbo'
```

Or with PowerShell 7:

```powershell
pwsh -NoProfile -File .\centinela_pc_return_readonly_preflight.ps1 -RepoPath 'E:\Github\MoneyPrinterTurbo'
```

The command prints:

- `PREFLIGHT_REPORT=<temp path>`
- `PREFLIGHT_SHA256=<hash>`
- `PREFLIGHT_HASH_FILE=<temp path>`
- `PREFLIGHT_COMPLETE=TRUE`

Return the report text plus SHA-256 for diagnosis. Do not treat `PREFLIGHT_COMPLETE=TRUE` as V1 certification.
