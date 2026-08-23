# R7 — Audiovisual Runtime V0.1

R7 connects the executable audiovisual stages of the Centinela production spine.

## Connected stages

`SCENES`
- Consumes the R6 `FinalScript` and its `FactLock`.
- Creates the canonical five-act `AstronomyVideoPlan`.
- Does not rerun an LLM.
- Does not trigger AI image/video generation.

`AUDIO`
- Runs the existing isolated Qwen3-TTS sidecar locally.
- Forces Hugging Face / Transformers offline mode.
- Uses the R6 pronunciation map only when token cardinality is preserved.
- Masters voice with FFmpeg two-pass `loudnorm`: `-16 LUFS`, `LRA 7`, `-1 dBTP`, 48 kHz.
- Qwen3-TTS currently exposes no native timestamp object to MPT, therefore R7 uses the already-installed local faster-whisper model.
- Whisper timestamps are aligned back to the approved script. Subtitle text authority remains the approved script, not ASR text.
- No model download is permitted.
- No music or sound asset is inserted automatically until an asset with verified rights is selected.

`VIDEO_BASE`
- Refuses unresolved scenes and irrelevant B-roll substitution.
- Reuses R4 MaterialSelection and SmartFocal evidence.
- Uses real TTS timings as the render timeline.
- Renders the social clean base at 1080×1920 / 30 fps with the existing Video Base renderer.
- Renders the 2160×3840 / 30 fps master directly from selected source media.
- The master is never produced by upscaling the social encode.
- Prefers NVENC with libx264 fallback.
- Creates a 1080×1920 audiovisual review preview using mastered voice.
- Keeps subtitles as a sidecar in R7; R8 owns review/finalization decisions.

## Guardrails

- `AUTO_PUBLICATION=False`
- no WanGP
- no external TTS
- no implicit model download
- no irrelevant B-roll fallback
- no architecture freeze
- clean social/master bases contain no audio
- review preview is not a publication artifact
- R8 remains the owner of `REVIEW_PREP` and publication-package materialization
