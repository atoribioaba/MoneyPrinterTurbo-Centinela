# Centinela physical-PC certification to 10/10

Target workstation: Windows 11 Pro / Ryzen 7 3700X / 16 GB RAM / RTX 2060 6 GB.

This document defines evidence required for dimensions that cannot honestly reach 10/10 in cloud.

## Gate 0 — pristine evidence before mutation

Run the existing read-only PC-return preflight first. Before its output is reviewed, do not run fetch/pull/switch/checkout/reset/clean/merge/rebase, do not restore/pop stash, do not update drivers and do not download models.

Capture:
- local branch/HEAD;
- dirty/untracked/stash state;
- canonical paths;
- physical D:/E: disk identity and MediaType;
- Windows version;
- NVIDIA driver and `nvidia-smi`;
- Python/uv;
- FFmpeg/FFprobe;
- Ollama/Tailscale presence.

## Gate 1 — safe Git reconciliation

Only after preservation:
1. push/preserve exact committed local lineage;
2. separately preserve untracked files and stash;
3. fetch remote refs;
4. compare local state against C20;
5. classify every difference as local-only, cloud-only, conflict, superseded or evidence-only;
6. create one dedicated reconciliation/RC branch;
7. port only required changes with targeted tests.

No blind bulk merge.

## Gate 2 — Windows regression

Required:
- Python 3.11 target environment reconstructed with uv;
- targeted tests for reconciliation deltas;
- fresh full pytest;
- path tests with accents, Unicode and spaces on the real drives;
- import/start/stop smoke;
- no secret regression.

## Gate 3 — AstroMedia real

Required:
- real catalog/database loads;
- known owned 4-video + 1-image fixture remains resolvable;
- rights = `CONFIRMED_OWNED` where expected;
- hashes/sidecars/provenance coherent;
- restricted/inadequate material fails closed;
- F57 real scenarios behave as designed.

## Gate 4 — GPU/CUDA

Do not infer GPU use from installation alone.

Evidence:
- `nvidia-smi` before workload;
- runtime logs naming the actual CUDA device when applicable;
- VRAM/process activity during selected GPU workload;
- exact dependency/runtime version using CUDA;
- CPU fallback behavior documented where relevant.

Driver CUDA capability, installed CUDA Toolkit and a dependency's CUDA runtime are three different facts and must be reported separately.

## Gate 5 — FFmpeg / NVENC / libx264

Capture exact `ffmpeg -version` and build configuration.

Required encode fixtures:
- `h264_nvenc` real encode succeeds on RTX 2060;
- output decodes with ffprobe;
- `libx264` fallback real encode succeeds;
- compare wall time, resulting bitrate/size and visual sanity on the same short source;
- listing `h264_nvenc` in `ffmpeg -encoders` is not certification.

## Gate 6 — video delivery

Real VIDEO_BASE:
- 1080x1920;
- 30 fps;
- expected audio-free state;
- relevant selected media only;
- SmartFocal/crop visually acceptable.

Real delivery:
- master 2160x3840 @ 30 fps;
- social 1080x1920 @ 30 fps;
- both rerendered from original source lineage;
- master is never an upscale of social;
- exact bytes hashed into render manifests.

## Gate 7 — LLM

For each selected local candidate:
- exact model/quantization;
- RAM/VRAM peak;
- generation latency;
- Spanish script quality;
- scientific instruction-following;
- failure/OOM behavior;
- deterministic/repeatability expectations documented.

Choose the best reasonable zero-cost model for this workstation, not the largest model that can barely load.

## Gate 8 — TTS/audio/subtitles

Use `TTS_ES_ES_A_B_ACCEPTANCE.md`.

Required:
- real male ES-ES listening test;
- astronomy pronunciation;
- long-form stability;
- RAM/VRAM/RTF;
- native timestamps assessed before Whisper;
- alignment/faster-whisper only if needed;
- final loudness/mastering checked on real output.

## Gate 9 — AI Visual

Only after explicit authorization for any multi-GB model download.

For T2I/I2V/T2V/upscale candidates:
- exact model/version/hash;
- license classification;
- peak RAM/VRAM;
- generation time;
- OOM/recovery;
- astronomy visual review;
- no generated asset may become `HECHO_VERIFICADO`;
- provenance must bind request/facts/model/prompts/asset bytes.

## Gate 10 — Golden E2E

A real project must traverse the canonical path and leave authoritative evidence through:
`RESEARCH → FACT LOCK → SCRIPT → SCENES → MEDIA → AUDIO/SUBTITLES → VIDEO_BASE → DELIVERY → REVIEW → PUBLICATION PACKAGE`.

Human Review 7/7 remains mandatory.

## Gate 11 — recovery / OSS / finalization

- run final Windows SBOM/inventory;
- exact FFmpeg/model/runtime licenses;
- execute non-destructive recovery drill;
- final F58 readiness;
- explicit human architecture/V1 freeze approval.

## 10/10 rule

No cloud simulation can satisfy a physical gate. A dimension reaches local 10/10 only when its evidence is attached to the final RC commit/run manifest.

`AUTO_PUBLICATION=FALSE`.
