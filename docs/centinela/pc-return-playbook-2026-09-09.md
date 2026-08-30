# PC return playbook — 2026-09-09

Purpose: make the first Windows session deterministic and avoid spending PC time reconstructing cloud history.

## Gate at session start

Do not install, update, rebase or merge before preservation.

Expected local source-of-truth checkpoint:

- branch `centinela-cert/golden-real-e2e-v0.1`
- HEAD `186104539a7116ad48b96beac90eccd3c4c37801`
- stash `22ee99b0703be803e63beaed2370485c84604c9a`
- 3 known untracked files documented in `cloud-local-reconciliation-manifest.md`

## Exact execution order

### 1. Identity and disk/runtime baseline

1. Confirm Windows date/time and PowerShell environment.
2. Confirm `E:` exists and determine SSD/HDD status if not already proven current.
3. Confirm repo path `E:\Github\MoneyPrinterTurbo`.
4. Read branch, HEAD, remotes and working-tree status without modifying them.

### 2. Preserve local state before touching remote lineage

5. Verify the expected local HEAD.
6. Verify stash object/message.
7. Hash and externally copy the three untracked files.
8. Capture status, local diffs, stash list and relevant hashes to an evidence folder.
9. Create/push a dedicated preservation branch only after independent backup exists.

### 3. Environment inventory — no upgrades yet

10. Capture Python, `uv`, Git, FFmpeg/ffprobe, Ollama and relevant package versions.
11. Capture `nvidia-smi` including driver, GPU, VRAM and reported CUDA compatibility.
12. Capture installed CUDA Toolkit as a separate fact; do not conflate driver CUDA, Toolkit and dependency runtime CUDA.
13. Check FFmpeg encoder availability for `h264_nvenc` and `libx264`.
14. Confirm local Qwen/Ollama models and Qwen3-TTS paths without downloading anything.
15. Confirm AstroMedia DB/catalog paths and own-media paths without recopying/deleting.

### 4. Cloud/local reconciliation

16. Fetch remote refs without merge/rebase.
17. Compare preserved local lineage with:
    - `centinela-backup/cloud-f57-8of8-20260830`;
    - `centinela-cert/cloud-mobile-v0.1`;
    - `centinela-cert/c3-f58-readiness-v0.1`.
18. Build file-level reconciliation matrix.
19. Selectively port only demonstrated cloud improvements in small batches.
20. Run targeted tests after each batch.

### 5. Full software regression

21. Run complete pytest on the reconciled candidate.
22. Resolve only demonstrated regressions/CI-hermetic issues; classify historical debt separately.
23. Re-run targeted FactLock, media specificity, rights/provenance, MaterialSelector and Publication Package guardrail tests.

### 6. Real material and F57

24. Verify actual AstroMedia catalog/database hashes and availability.
25. Re-run Lunar with real local evidence; require MEDIA 5/5 or fail closed.
26. Run all 8 F57 scenarios locally with real/local contracts.
27. `INSUFFICIENT_MEDIA` must remain a controlled fail/NEEDS_INPUT scenario.
28. `VISUAL_RECREATION` must remain explicitly labeled and never represent a real observation/event.
29. Require `oom_events=0` and `unrecovered_failures=0` for final F57 evidence.

### 7. Voice, subtitles and audio

30. Validate local Qwen3-TTS runtime with the approved Spanish-Spain male documentary/cinematic profile.
31. Capture runtime, RAM/VRAM and stability evidence.
32. Prefer reliable TTS timestamps for subtitles; use faster-whisper only as fallback/alignment when needed.
33. Validate textual subtitle authority against the approved script.
34. Validate audio master target around -16 LUFS, LRA ~7, -1 dBTP, 48 kHz.

### 8. RTX 2060 / encode certification

35. Demonstrate actual GPU use with `nvidia-smi`/runtime evidence.
36. Run a real `h264_nvenc` smoke encode.
37. Run an equivalent `libx264` fallback encode.
38. Compare compatibility, quality, time and stability briefly.
39. Keep `libx264` fallback even if NVENC wins.

### 9. Full real Golden

40. Execute complete real Golden E2E from research through VIDEO_BASE.
41. Require 9:16 social `1080x1920`, master `2160x3840`, 30 fps.
42. Inspect scientific correctness, visual relevance, brightness/readability, subtitles, audio, thumbnail, rights/provenance.
43. Stop at human review.

### 10. Publication Package

44. After human content approval, generate/review the manual Publication Package:
    - `master_2160x3840.mp4`;
    - `social_1080x1920.mp4`;
    - `thumbnail.jpg`;
    - `subtitles-es.srt`;
    - captions/copy;
    - YouTube title/description;
    - hashtags;
    - sources/licenses/provenance;
    - metadata;
    - review checklist.
45. `APPROVED` still does not mean authorized to publish.
46. Keep `AUTO_PUBLICATION=FALSE`.

### 11. C3 final OSS/SBOM

47. Generate full transitive Python SBOM from the actual frozen environment.
48. Audit FFmpeg actual build license/configuration.
49. Audit exact Ollama/Qwen/Qwen3-TTS/faster-whisper and vision-stack versions/licenses used.
50. Finish canonical pipeline OSS table:
    `Función | Actual | Mejor candidato OSS | Gratuito | Licencia | VRAM/RAM | Mejora | Decisión`.
51. Unknown license remains `LICENCIA NO VERIFICADA` and blocks `oss_audit_complete` if included in F58.

### 12. F58 and freeze

52. Run F58 readiness audit.
53. Require operational hardening not blocked.
54. Require real Golden `CERTIFICATION_PASS`.
55. Require Publication Package `READY_FOR_MANUAL_PACKAGE`.
56. Require analytics adapter operational.
57. Require all supplied OSS audit entries verified.
58. Expected status before explicit user approval: `READY_FOR_HUMAN_FREEZE_APPROVAL`.
59. Architecture freeze may be authorized only after explicit human approval; F58 itself must never execute the freeze.

## Explicitly forbidden during the return session

- destructive Git history/worktree operations that can discard local evidence;
- force-updating remote history;
- deleting stash/untracked state before backup;
- blind merge cloud→local;
- weakening tests/scientific/material/rights gates;
- downloading Qwen3.8 or other multi-GB models without authorization;
- changing NVIDIA driver/CUDA Toolkit without demonstrated need;
- deleting/recopying the existing own-media corpus without evidence;
- automatic publication.

## Success criterion for the first PC phase

The session is successful when the reconciled local candidate is preserved, reproducible and fully tested, and the only remaining transition is human acceptance/freeze — not when the WebUI merely opens.
