# Centinela Cloud Certification Checkpoint

This file records the remote C2/F57 certification checkpoint used while the local Windows workstation is unavailable.

## Scope and safety

- Certification branch: `centinela-cert/cloud-mobile-v0.1`
- Remote base: `centinela-production/av-runtime-v0.1`
- Base SHA: `ad28ca201fc7fc444879c823ab68dbd166d03f2b`
- MaterialSelector remains final authority.
- Semantic matching remains secondary evidence only.
- SmartFocal remains post-selection only.
- No irrelevant B-roll fallback.
- No automatic AI generation.
- No automatic publication.
- External/network discovery remains disabled by default for certification.
- A cloud PASS is not a substitute for the later local Golden certification.

## Applied and proven in the cloud branch

### C2.11J scientific specificity

1. A genuinely generic Moon scene may use generic Moon media.
2. A scientifically specific lunar scene may not pass from object identity alone.
3. Spanish/English body aliases are lexical evidence only and must not synthesize strong `astronomy_objects` overlap.
4. A scene with missing structured body grounding and a specific scientific requirement fails closed against generic media.
5. Specific secondary evidence, for example Moon + Capricornus for a constellation map, may satisfy the specificity guard.

### Deterministic FactLock scientific visuals

- Lunar angular-diameter diagram is generated locally and deterministically from FactLock.
- Lunar visual-magnitude diagram is generated locally and deterministically from FactLock.
- Output is 1080x1920 PNG with AstroMedia sidecar + FactLock manifest.
- No network calls.
- No generative AI.
- Publication still requires human review.

### Lunar V31-class hermetic MEDIA replay

The five Lunar V31 scene classes are represented by hermetic fixtures and scientific visuals.

Expected and achieved targeted contract:

- scene_count = 5
- selected_count = 5
- unresolved_count = 0
- no irrelevant B-roll
- no AI-generated selection
- no auto-publication
- no synthetic strong Moon object for the scene-5 lexical bridge

This is a cloud/hermetic MEDIA proof only. It does not certify the real local AstroMedia catalog or local hardware/runtime.

## Current gate — full repository regression

The next blocking step is to close the full-repository regression on the cloud branch before expanding F57.

Known latest regression state on the pre-checkpoint-update certification commit:

- Linux / Python 3.11: full-regression Ruff gate failed before pytest.
- Linux / Python 3.13: Ruff gate passed; full pytest/coverage gate failed.
- Windows / Python 3.11: compile/Ruff/focused certification passed; Windows path-policy smoke failed.

Required handling:

1. Recover the exact failing diagnostics.
2. Classify each as `REGRESSION_NEW`, `CI_HERMETICITY`, or `HISTORICAL_DEBT`.
3. Fix only demonstrated regressions or CI defects.
4. Do not weaken selectors, scientific gates, tests, path policy, provenance, or fail-closed behavior merely to obtain green CI.
5. Re-run the Linux 3.11, Linux 3.13 and Windows 3.11 gates.

## F57 roadmap after Lunar regression closes

1. LUNAR — cloud MEDIA 5/5 achieved; full regression pending.
2. SOL_TO_MOON — next recommended scenario after Lunar closes.
3. PLANETARY.
4. ECLIPSE.
5. CONSTELLATION.
6. DEEP_SKY.
7. INSUFFICIENT_MEDIA — must fail closed rather than fabricate or insert irrelevant B-roll.
8. VISUAL_RECREATION — must remain explicitly labelled as visual recreation and separated from documentary/scientific media.

Each scenario must eventually provide evidence for:

- scientific_pass
- visual_relevance_pass
- provenance_pass
- render_pass
- no_irrelevant_broll
- recovery_pass

## Mobile/cloud review track

A separate draft branch/PR provides a safe interactive WebUI preview for mobile review. It is demo-only and does not access the local workstation, local AstroMedia, local Qwen runtime, secrets, rendering or publication.

Cloud work may generate reviewable artifacts for the phone: scientific PNGs, JSON/JUnit evidence, WebUI screenshots/previews, TTS A/B samples when a suitable cloud-safe runtime is available, and deterministic FFmpeg preview videos.

## Mandatory local reconciliation later

The later local certification state is not present byte-for-byte in GitHub. When the Windows workstation is available again, the cloud patchset must be reconciled safely with the exact local certification line before claiming final certification.

Local-only or local-required evidence includes:

- real AstroMedia catalog and local paths;
- Qwen3-TTS local runtime/voice quality;
- RTX 2060 CUDA evidence;
- NVENC versus libx264 fallback on the real GPU;
- RAM/VRAM/OOM and recovery measurements;
- real Golden production through human review;
- final F57/F58 certification and human architecture-freeze approval.

No merge to production, no publication and no architecture freeze are implied by this checkpoint.
