# Cloud pre-PC checkpoint — 2026-08-30

Purpose: preserve the maximum cloud-side progress before the Windows/RTX workstation is available again on **2026-09-09**. This is operational evidence, not an architecture freeze and not permission to merge or publish.

## Guardrails

- `MERGE_AUTHORIZED=FALSE`
- `ARCHITECTURE_FREEZE_AUTHORIZED=FALSE`
- `AUTO_PUBLICATION=FALSE`
- `CLOUD_PASS_IS_NOT_LOCAL_CERTIFICATION=TRUE`
- `LOCAL_VALIDATION_REQUIRED=TRUE`
- `HUMAN_REVIEW_REQUIRED=TRUE`

## F57 — cloud closure

The eight canonical cloud scenarios are complete:

1. `SOL_TO_MOON`
2. `LUNAR`
3. `PLANETARY`
4. `ECLIPSE`
5. `CONSTELLATION`
6. `DEEP_SKY`
7. `INSUFFICIENT_MEDIA`
8. `VISUAL_RECREATION`

Exact preserved F57 checkpoint, re-verified on 2026-08-30:

- branch: `centinela-backup/cloud-f57-8of8-20260830`
- commit: `a88f08fe9ae44cb24dafd8044a7b0b45e678d5d6`

Interpretation:

- `F57_CLOUD=8/8_PASS`;
- `INSUFFICIENT_MEDIA` proves the controlled fail-closed/recovery path;
- `VISUAL_RECREATION` remains explicitly labeled as recreation, does not represent a real observation/event and is not publication-ready without human review;
- local RTX/NVENC/performance/real-media certification remains pending.

## C3 / F58 preparation

Working branch: `centinela-cert/c3-f58-readiness-v0.1`.

Cloud-side preparation now includes:

- F57 evidence index;
- F58 readiness mechanism and freeze guardrails;
- provisional OSS/SBOM audit;
- cloud-side dependency/provider license closure;
- Qwen/TTS local-certification preparation;
- Publication Package readiness preparation;
- first real `SOL_TO_MOON` production pre-brief;
- reproducible CycloneDX SBOM workflow `.github/workflows/centinela-c3-sbom.yml`;
- isolated GitHub Actions pre-step diagnostic.

## GitHub Actions blocker — verified scope

Dedicated F58 run:

- run id: `33323286894`;
- second controlled attempt performed on 2026-08-30;
- Linux 3.11, Linux 3.13 and Windows 3.11 fail before any workflow step executes;
- no usable step/log evidence is exposed.

Minimal isolated probe:

- branch: `centinela-diagnostics/actions-prestep-probe-20260830`;
- commit: `4fb3de881da9b8d4692387f34b4f8268a8e63aa4`;
- workflow: `Centinela Actions Pre-step Probe`;
- run id: `33325885812`;
- workload: `ubuntu-latest` plus one intended shell `echo`, with no checkout, Python, uv, dependencies, secrets or project imports;
- result: failure before the intended step, `steps=null`.

Verified classification:

`CI_PRE_STEP_EXECUTION_BLOCKER / CONTROL_PLANE`

This rules out F58 application code, Python, uv, dependencies, Ruff/pytest and Centinela/MoneyPrinterTurbo product logic as the cause. The unresolved root-cause set is repository/account Actions execution control: runner allocation, quota/billing, policy/permissions or an equivalent GitHub control-plane condition.

The public GitHub Status page did not show a current global Actions incident when checked after the probe, therefore a global runner outage is not asserted.

Detailed record:

`docs/centinela/actions-prestep-diagnostic-20260830.md`

Operational rule:

- `PATCH_PRODUCT_CODE=FALSE`
- `BLIND_RERUN_LOOP=FALSE`
- `F58_APPLICATION_REGRESSION=NOT_DEMONSTRATED`
- first recover the Actions execution condition;
- then run the minimal probe once;
- only if `CENTINELA_ACTIONS_STEP_EXECUTION=PASS` appears, re-run F58 and the SBOM workflow.

## OSS / license state

Static cloud closure:

`docs/centinela/c3-cloud-oss-license-closure-20260830.md`

Key decisions:

- local-first V1 remains the target;
- OpenAI, DashScope and Google GenAI clients are separated from their hosted services and are not selected as the local-primary V1 path;
- Azure Speech SDK is proprietary and is not an OSS V1 primary component;
- TwelveLabs is optional/not selected for local V1; exact SDK license remains fail-closed `LICENCIA NO VERIFICADA`;
- `CycloneDX Python / cyclonedx-bom 7.3.1` is the primary Python SBOM generator;
- Syft is optional later cross-check only;
- `F58_OSS_AUDIT_COMPLETE=FALSE` until exact installed/runtime/model evidence exists.

Prepared SBOM workflow behavior once Actions can execute steps:

1. `uv sync --frozen --python 3.11` from checked-in `uv.lock`;
2. export exact resolved Python inventory;
3. generate reproducible CycloneDX 1.6 JSON;
4. validate structure;
5. SHA-256 hash the evidence;
6. upload SBOM/inventory/hash artifact.

## PR safety

PR #1 — `C2.11J cloud certification: scientific media specificity` — is currently:

- OPEN;
- DRAFT;
- mergeable according to GitHub metadata;
- NOT MERGED;
- base `centinela-production/av-runtime-v0.1` @ `ad28ca201fc7fc444879c823ab68dbd166d03f2b`;
- head `centinela-cert/cloud-mobile-v0.1` @ `1d335c189fac23e1671b7e8030b365c3c74eca73`.

Do not merge before cloud↔local reconciliation.

PR #2 — WebUI cloud preview — remains a separate draft demo path. It may support mobile UI/UX review only; it must not be treated as local hardware/runtime certification.

## Local state that must not be overwritten

Last trusted local baseline:

- branch: `centinela-cert/golden-real-e2e-v0.1`;
- HEAD: `186104539a7116ad48b96beac90eccd3c4c37801`;
- exact local commit is not represented by the current remote lineage;
- stash: `22ee99b0703be803e63beaed2370485c84604c9a`;
- stash label: `C2.11O-M V34 pre-V33 preserve 20260826-172847`;
- known pre-V33 untracked files:
  - `app/services/centinela/quality/f57_real_runner.py`
  - `test/services/test_f57_real_runner.py`
  - `test/services/test_public_source_rights.py`
- V36 evidence says original pre-V33 dirty state was restored and the stash was applied, not popped.

Never blind pull/merge/rebase/reset over this state.

## Remaining work possible without the PC

1. identify or resolve the GitHub Actions pre-step execution blocker from account/repository controls;
2. once the minimal probe can execute its step, run F58 once;
3. collect F58 JUnit/evidence for Linux 3.11, Linux 3.13 and Windows 3.11;
4. execute the prepared C3 Python SBOM workflow once;
5. retain CycloneDX JSON, resolved package inventory and SHA-256 evidence;
6. update cloud OSS audit with that transitive graph without calling it Windows-final;
7. inspect PR #1 for unexpected drift before 2026-09-09;
8. keep Issues #3/#5 synchronized with new evidence;
9. preserve any new cloud closure in an immutable-by-convention backup branch;
10. use PR #2 only for safe mobile UI/UX review if useful;
11. do not freeze date-sensitive astronomy for the first real `SOL_TO_MOON` before a real production date/location is selected.

## Hard local gates — 2026-09-09+

These cannot be certified in cloud:

- preserve/hash exact local Git state and untracked files;
- selectively reconcile local `186104...` with cloud changes;
- targeted tests plus fresh full pytest;
- actual AstroMedia catalog/database/media/sidecars;
- owned-media hashes, rights and provenance;
- real Lunar MEDIA 5/5;
- required F57 local/real evidence;
- Qwen3-TTS real ES-ES quality/stability/performance/timestamps;
- faster-whisper fallback measurements if required;
- RTX 2060 actual CUDA-use proof;
- real `h264_nvenc` smoke/encode;
- `libx264` fallback comparison;
- RAM/VRAM/OOM measurements;
- actual Windows FFmpeg build/configuration/license mode;
- exact Ollama version and Qwen3.5 digest/quantization;
- exact Qwen3-TTS artifact/revision/hash;
- exact faster-whisper/CTranslate2/CUDA runtime;
- exact CLIP/Florence weights/license evidence if used by final SmartFocal;
- final Windows transitive SBOM;
- full real Golden E2E;
- human science/visual/audio/subtitle/rights review;
- manual Publication Package proof;
- final canonical OSS pipeline audit;
- F58 final readiness;
- explicit human architecture-freeze approval.

## Exact return-to-PC order

1. verify local branch and HEAD;
2. capture `git status --porcelain=v1` before changes;
3. verify known stash exists; do not pop it;
4. verify/hash the three known untracked files;
5. push/preserve exact committed local lineage to a dedicated backup branch;
6. separately preserve dirty/untracked state without destructive cleanup;
7. fetch remote refs only;
8. compare local `186104...` with cloud checkpoints/PR #1;
9. create a dedicated reconciliation branch and port only demonstrated cloud changes;
10. run targeted tests for each port;
11. run fresh full pytest;
12. validate real AstroMedia database/catalog/media/sidecars;
13. re-check owned media without recopying/deleting it;
14. run real Lunar and require MEDIA 5/5 or fail closed;
15. run/reconfirm required F57 real/local contracts;
16. certify Qwen3-TTS locally;
17. certify subtitle timestamp path and measure faster-whisper fallback if needed;
18. prove RTX 2060/CUDA use from runtime evidence;
19. prove `h264_nvenc` with real encode;
20. prove `libx264` fallback and compare briefly;
21. record RAM/VRAM/OOM;
22. capture final Windows SBOM/runtime/model evidence;
23. run full real Golden E2E to `READY_FOR_HUMAN_REVIEW`;
24. perform human review;
25. if approved, produce/verify manual Publication Package;
26. finish canonical OSS audit table;
27. run F58 final readiness;
28. request explicit human freeze approval;
29. only after approval mark V1 frozen;
30. start first real `SOL_TO_MOON` from the pre-brief using current primary-source astronomy.

## Cloud-complete definition before 2026-09-09

Cloud is maximally complete when F57 remains preserved 8/8; PRs remain unmerged/recoverable; the Actions control-plane blocker is either resolved or precisely documented; F58/SBOM executable evidence is captured if step execution becomes available; static dependency/provider licensing is closed; the return/reconciliation procedure is explicit; the first real `SOL_TO_MOON` has a pre-brief but no stale ephemerides; and no cloud evidence is misrepresented as Windows/RTX/local certification.
