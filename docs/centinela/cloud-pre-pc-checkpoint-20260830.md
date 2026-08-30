# Cloud pre-PC checkpoint — 2026-08-30

Purpose: preserve the maximum cloud-side progress before the Windows/RTX workstation is available again on **2026-09-09**. This checkpoint is operational evidence, not an architecture freeze and not permission to merge or publish.

## Global guardrails

- `MERGE_AUTHORIZED=FALSE`
- `ARCHITECTURE_FREEZE_AUTHORIZED=FALSE`
- `AUTO_PUBLICATION=FALSE`
- `CLOUD_PASS_IS_NOT_LOCAL_CERTIFICATION=TRUE`
- `LOCAL_VALIDATION_REQUIRED=TRUE`
- `HUMAN_REVIEW_REQUIRED=TRUE`

## Cloud state reached by 2026-08-30

### F57

Cloud scenario regression is complete for all eight canonical scenarios:

1. `SOL_TO_MOON`
2. `LUNAR`
3. `PLANETARY`
4. `ECLIPSE`
5. `CONSTELLATION`
6. `DEEP_SKY`
7. `INSUFFICIENT_MEDIA`
8. `VISUAL_RECREATION`

Preserved recovery point:

- branch: `centinela-backup/cloud-f57-8of8-20260830`
- commit: `a88f08fb9f7a372df1ae14c552ac70848e89f31e`

Interpretation:

- cloud F57 logic/evidence: complete;
- `INSUFFICIENT_MEDIA`: controlled fail-closed/recovery path, not a false production pass;
- `VISUAL_RECREATION`: explicitly AI/recreation labeled, does not represent a real observation/event, not publication-ready without review;
- local RTX/NVENC/performance/real-media final certification remains pending.

### C3 / F58 preparation

Working branch: `centinela-cert/c3-f58-readiness-v0.1`.

Cloud-side work completed before this checkpoint includes:

- F57 8/8 evidence index;
- F58 readiness mechanism and freeze guardrails;
- provisional OSS/SBOM audit;
- cloud-side active-pipeline license audit;
- Qwen/TTS local-certification preparation;
- Publication Package readiness preparation;
- first real `SOL_TO_MOON` production pre-brief;
- reproducible CycloneDX SBOM workflow prepared as `.github/workflows/centinela-c3-sbom.yml`.

The SBOM workflow intentionally uses `workflow_dispatch` only. It must not be converted into a noisy automatic loop while CI jobs are terminating before any workflow step starts.

### F58 pre-step CI blocker

Correct dedicated F58 workflow run:

- run id: `33323286894`
- workflow: `Centinela C3 F58 Readiness Mechanism`
- branch: `centinela-cert/c3-f58-readiness-v0.1`
- second controlled attempt performed on 2026-08-30;
- Windows 3.11, Linux 3.11 and Linux 3.13 all fail before a workflow step starts;
- jobs expose no usable step execution/log evidence;
- the public GitHub Status page did not show a current Actions outage at the time of the second diagnosis.

Verified classification:

`CI_PRE_STEP_EXECUTION_BLOCKER`

What is proven: application/test code did not execute, so this failure is **not evidence of an application/test regression**.

What is not yet proven with the available evidence: whether the pre-step blocker is hosted-runner assignment, repository/account Actions quota or billing, a repository policy/permission condition, or another control-plane condition.

Do not patch product code to compensate for this blocker. Re-run only after there is evidence that a job can actually enter step execution or after the account/repository control-plane condition is identified and resolved.

### OSS / license state

Cloud/static dependency license closure is recorded in:

`docs/centinela/c3-cloud-oss-license-closure-20260830.md`

Important decisions:

- local-first V1 remains the target;
- OpenAI, DashScope and Google GenAI clients may be OSS packages but their hosted APIs are separate external services and are not selected as the V1 local-primary path;
- Azure Speech SDK is proprietary and is not an OSS V1 primary component;
- TwelveLabs remains optional/not selected for local V1 and its exact SDK license is fail-closed as `LICENCIA NO VERIFICADA` in this audit;
- `CycloneDX Python / cyclonedx-bom 7.3.1` is the primary V1 Python SBOM generator;
- Syft remains an optional later cross-check, not a V1 requirement.

`F58_OSS_AUDIT_COMPLETE=FALSE` until exact installed/runtime/model evidence is captured.

## Remote branch / PR safety

### PR #1

`C2.11J cloud certification: scientific media specificity` remains:

- OPEN;
- DRAFT;
- NOT MERGED.

Do not merge before cloud↔local reconciliation.

### Local state that must not be overwritten

The last trusted local baseline remains:

- branch: `centinela-cert/golden-real-e2e-v0.1`
- HEAD: `186104539a7116ad48b96beac90eccd3c4c37801`
- this exact commit is not represented by the current remote lineage and must be preserved before reconciliation;
- stash: `22ee99b0703be803e63beaed2370485c84604c9a`
- stash label: `C2.11O-M V34 pre-V33 preserve 20260826-172847`
- pre-V33 untracked files:
  - `app/services/centinela/quality/f57_real_runner.py`
  - `test/services/test_f57_real_runner.py`
  - `test/services/test_public_source_rights.py`
- V36 evidence says the original pre-V33 dirty state was restored and the stash was applied, not popped.

Never perform a blind pull/merge/rebase/reset over this state.

## Work that can still be done without the PC

Only evidence-producing cloud work is useful now. The remaining cloud queue is:

1. identify/resolve the GitHub Actions pre-step execution blocker, or wait for evidence that runners can enter step execution;
2. once a job can start steps, run the dedicated F58 contract once;
3. collect Linux 3.11, Linux 3.13 and Windows 3.11 JUnit/evidence from F58;
4. execute `Centinela C3 Python SBOM` once and retain the CycloneDX JSON, resolved inventory and SHA-256 evidence;
5. update the OSS audit with the resulting transitive cloud graph without claiming it is the Windows-final graph;
6. inspect PR #1 for unexpected drift before 2026-09-09;
7. keep Issues #3/#5 synchronized with any new evidence;
8. preserve any new cloud closure in a dedicated immutable-by-convention backup branch;
9. perform cloud/WebUI/mobile review only where it tests navigation, contracts or presentation; never label it RTX/CUDA/NVENC/local-runtime certification;
10. do not freeze date-sensitive astronomy for first `SOL_TO_MOON` until a real production date/location is chosen.

## Work that cannot be certified without the PC

These remain hard local gates:

- preserve and hash the exact local Git state;
- reconcile local `186104...` with cloud changes selectively;
- full local pytest/regression on the reconciled branch;
- real AstroMedia catalog/files and sidecars;
- real own-media hashes/rights/provenance checks;
- Lunar real MEDIA 5/5 on the local catalog;
- all F57 scenarios against the reconciled/local environment where required;
- Qwen3-TTS real local voice quality/stability/performance;
- subtitle timestamp path and faster-whisper fallback measurements;
- RTX 2060 CUDA/runtime proof;
- `h264_nvenc` smoke and real encode;
- `libx264` fallback comparison;
- RAM/VRAM/OOM measurements;
- actual FFmpeg build configuration/license mode;
- exact Ollama version and Qwen3.5 model digest/quantization;
- exact Qwen3-TTS artifact/model revision/hash;
- exact faster-whisper/CTranslate2/CUDA runtime;
- exact selected CLIP/Florence weights and license evidence if those weights are used by the final V1 SmartFocal path;
- complete real Golden E2E;
- human review;
- manual Publication Package final proof;
- final OSS audit;
- F58 final state;
- human architecture freeze approval.

## Exact return-to-PC sequence — 2026-09-09+

Run in this order; do not skip preservation steps:

1. verify current local branch and HEAD;
2. capture `git status --porcelain=v1` before changes;
3. verify the known stash exists and do not pop it;
4. verify the three known untracked files and hash them;
5. create/push a dedicated remote backup of the exact committed local lineage before reconciliation;
6. preserve the dirty/untracked state separately without destructive cleanup;
7. fetch remote refs only;
8. compare local `186104...` against cloud checkpoints and PR #1; do not merge blindly;
9. port only demonstrated cloud fixes/features into a dedicated reconciliation branch;
10. run targeted tests for every selectively ported area;
11. run the full local pytest suite;
12. validate actual AstroMedia DB/catalog/media files and sidecars;
13. re-check the owned media corpus without recopying/deleting it;
14. run real Lunar selection and require MEDIA 5/5 or fail closed;
15. run/reconfirm the remaining F57 real/local contracts needed for final evidence;
16. certify Qwen3-TTS locally with the intended male ES-ES documentary/cinematic profile;
17. certify subtitle timestamps; use faster-whisper only when needed and measure it;
18. prove RTX 2060/CUDA use from runtime evidence, not installation assumptions;
19. prove `h264_nvenc` path with a real smoke/encode;
20. prove `libx264` fallback and compare briefly;
21. record RAM/VRAM/OOM behavior during representative work;
22. capture final Windows transitive SBOM plus exact non-Python/runtime/model evidence;
23. run the full real Golden E2E to `READY_FOR_HUMAN_REVIEW`;
24. perform human science/visual/audio/subtitle/rights review;
25. if approved, produce and verify the manual Publication Package;
26. finish the canonical OSS pipeline audit table;
27. run F58 final readiness;
28. request explicit human architecture-freeze approval;
29. only after approval, mark V1 frozen;
30. start the first real `SOL_TO_MOON` production from the existing pre-brief and current primary-source astronomy.

## Definition of cloud-complete before 2026-09-09

Cloud work is considered maximally complete when:

- F57 remains preserved 8/8;
- PR #1 remains unmerged and recoverable;
- F58 code/contract is prepared;
- F58 pre-step failure is correctly classified rather than patched around;
- cloud transitive SBOM is captured if CI step execution becomes available, otherwise the workflow and audit contract are ready;
- active dependency/provider licensing is statically classified;
- local return/reconciliation procedure is immutable and explicit;
- the first real `SOL_TO_MOON` production has a pre-brief but no stale ephemerides;
- no claim is made that cloud CI replaces Windows/RTX/local certification.
