# F57 Cloud Certification — 8/8 Manifest

Date: 2026-08-30
Project: EL CENTINELA DEL UNIVERSO × MONEYPRINTERTURBO
Scope: CLOUD CERTIFICATION ONLY

## Canonical checkpoint

- Backup branch: `centinela-backup/cloud-f57-8of8-20260830`
- Exact certified commit: `a88f08fe9ae44cb24dafd8044a7b0b45e678d5d6`
- `CLOUD_PASS_IS_NOT_LOCAL_CERTIFICATION=TRUE`
- `LOCAL_VALIDATION_REQUIRED=TRUE`
- `MERGE_AUTHORIZED=FALSE`
- `AUTO_PUBLICATION=FALSE`
- `FREEZE_AUTHORIZED=FALSE`

## F57 scenarios

| # | Scenario | Cloud status |
|---:|---|---|
| 1 | SOL_TO_MOON | PASS |
| 2 | LUNAR | PASS |
| 3 | PLANETARY | PASS |
| 4 | ECLIPSE | PASS |
| 5 | CONSTELLATION | PASS |
| 6 | DEEP_SKY | PASS |
| 7 | INSUFFICIENT_MEDIA | PASS |
| 8 | VISUAL_RECREATION | PASS |

`F57_CLOUD_RESULT=8/8_PASS`

## Required evidence contract

Every normal scenario is certified against the F57 evidence contract:

- `scientific_pass`
- `visual_relevance_pass`
- `provenance_pass`
- `render_pass`
- `no_irrelevant_broll`
- `recovery_pass`

`INSUFFICIENT_MEDIA` additionally proves fail-closed behavior: 4/5 media -> `NO_ADEQUATE_MEDIA` -> CLEAN_BASE blocked -> add scientifically relevant M57 -> 5/5.

`VISUAL_RECREATION` proves the explicit AI recreation route. AI media is accepted only through the two explicit permissions (`allow_ai_last_resort` + scene `ai_recreation_allowed`), remains `RECREACION_VISUAL`, requires human review, is not represented as a real observation/event, and is not publication-ready automatically.

### VISUAL_RECREATION exact cloud evidence

- GitHub Actions run: `33320062923`
- Linux Python 3.11: PASS including Ruff, render and F57 gate
- Linux Python 3.13: PASS
- Windows Python 3.11: PASS
- Render/evidence/manifest SHA-256: `e452d3a2876a2cdc839b42a9a8e15545da73197965dff4cb564f4bc12b4f2a03`
- `represents_real_observation=false`
- `represents_real_event=false`
- `production_astronomy_media=false`
- `publication_ready=false`
- `auto_publication=false`
- `human_review_required=true`

## Interpretation

This closes **C2/F57 in cloud**. It does not certify the Windows workstation, RTX 2060, local AstroMedia catalog, local Qwen3-TTS, CUDA/NVENC, RAM/VRAM/OOM behavior, or the real Golden E2E. Those remain mandatory local evidence before V1 freeze.
