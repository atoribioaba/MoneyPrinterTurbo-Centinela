# No-PC cloud execution plan — 2026-08-30 → 2026-09-09

Objective: complete every task that can be honestly performed from GitHub/cloud/mobile before the Windows workstation returns, leaving only local-state, real-media and hardware authority for the PC.

## Global status at plan start

- `F57_CLOUD=8/8_PASS`
- exact F57 checkpoint: `a88f08fe9ae44cb24dafd8044a7b0b45e678d5d6`
- F57 recovery branch: `centinela-backup/cloud-f57-8of8-20260830`
- C3/F58 branch: `centinela-cert/c3-f58-readiness-v0.1`
- C3/F58 Actions run `33321688545`: all jobs stopped before step execution; classified `CI_INFRASTRUCTURE_RUNNER_STARTUP_BLOCKER`
- `LOCAL_CERTIFICATION_REQUIRED=TRUE`
- `MERGE_AUTHORIZED=FALSE`
- `AUTO_PUBLICATION=FALSE`
- `ARCHITECTURE_FREEZE_AUTHORIZED=FALSE`

## Workstream A — continuity, evidence and recovery

1. Preserve exact F57 cloud checkpoint. **DONE**
2. Keep C2.11J Lunar checkpoint separately recoverable. **DONE**
3. Refresh reconciliation issue with F57 8/8 while retaining local `186104...` authority. **DONE 2026-08-30**
4. Capture cloud↔local reconciliation manifest in repository. **DONE 2026-08-30**
5. Capture deterministic PC-return playbook. **DONE 2026-08-30**
6. At end of no-PC phase, create one final C3 cloud backup branch/tag-like checkpoint by project convention. **PENDING LAST CLOUD STEP**
7. Record final C3 head/tree and evidence index. **PENDING LAST CLOUD STEP**

## Workstream B — C3/F58 mechanism

1. Keep F58 audit-only/fail-closed semantics. **DONE**
2. Keep freeze execution impossible inside F58. **DONE**
3. Keep human approval separate from technical readiness. **DONE**
4. Keep incomplete OSS audit and Publication Package as blockers. **DONE**
5. Obtain executable Linux 3.11 evidence. **BLOCKED BY RUNNER STARTUP**
6. Obtain executable Linux 3.13 evidence. **BLOCKED BY RUNNER STARTUP**
7. Obtain executable Windows 3.11 evidence. **BLOCKED BY RUNNER STARTUP**
8. Re-dispatch once runner/account execution is restored; do not spam retries. **PENDING CONDITION**
9. If execution begins, retain JUnit and guardrail artifacts. **PENDING CONDITION**
10. Classify any actual test failure as new regression, CI hermeticity or historical debt before code changes. **PENDING CONDITION**

## Workstream C — OSS audit and SBOM

1. Capture direct dependency manifest from `pyproject.toml`. **DONE 2026-08-30**
2. Capture repository version/Python/license declaration. **DONE**
3. Build provisional cloud OSS/SBOM document. **DONE 2026-08-30**
4. Verify licenses for active pipeline runtimes/libraries from primary sources. **IN PROGRESS**
5. Separate code/runtime licenses from hosted service terms. **IN PROGRESS**
6. Mark optional commercial/provider SDKs not selected for zero-cost local V1. **PENDING**
7. Audit model-weights licenses separately from runtime licenses. **PENDING**
8. Generate full transitive Python SBOM when runner execution is available. **PENDING RUNNER**
9. Leave only exact local-build facts for PC: installed graph, FFmpeg build/config/license, actual model hashes/versions and runtime RAM/VRAM. **PC-ONLY**

## Workstream D — Publication Package cloud contract

1. Audit current schema/service against the canonical package. **DONE 2026-08-30**
2. Current implementation explicitly plans master, social, caption, metadata and publication checklist. **VERIFIED**
3. Canonical contract additionally requires thumbnail, subtitles and explicit sources/licenses/provenance deliverables. **GAP IDENTIFIED**
4. Define backward-compatible v0.2 request/asset contract without enabling writes/uploads/publication. **PENDING CLOUD**
5. Add synthetic planning-only tests for all required assets. **PENDING CLOUD**
6. Add fail-closed readiness test when a required package asset is unavailable. **PENDING CLOUD**
7. Keep `manual_publication_only=true`, `writes_files=false`, `uploads_files=false`, `network_calls=0`, `auto_publication=false`. **NON-NEGOTIABLE**
8. Execute dry-run contract in CI when runner is available. **PENDING RUNNER**
9. Real files and human approval remain PC-only. **PC-ONLY**

## Workstream E — WebUI mobile preview

1. Keep PR #2 draft and non-mergeable/non-production. **DONE/ONGOING**
2. Retain demo-only safety boundary: no local drives, API keys, Ollama/Qwen local, rendering or publication. **DONE**
3. Reconcile preview terminology with canonical stages: Investigación → FactLock → Guion → Escenas → Media → Voz → Subtítulos → Vídeo → Revisión → Publicación. **PENDING CLOUD**
4. Update preview to reflect F57 cloud 8/8 without claiming local certification. **PENDING CLOUD**
5. Remove/avoid demo wording that could be mistaken for real local evidence. **PENDING CLOUD**
6. Add explicit Publication Package completeness panel. **PENDING CLOUD**
7. Validate responsive layouts at representative desktop/tablet/mobile widths when browser/CI tooling is executable. **PENDING RUNNER/BROWSER**
8. Temporary tunnel remains optional review tooling only. **ONGOING**

## Workstream F — LLM/TTS decision documentation

1. Keep local V1 LLM candidate `qwen3.5:4b-q4_K_M` as current selected baseline. **DECIDED**
2. Keep Qwen3.8 A/B deferred because 27B-class local footprint is a poor fit for RTX 2060 6 GB + 16 GB RAM. **DECIDED**
3. Do not download Qwen3.8 while PC is absent. **LOCKED**
4. Capture Qwen3.8 decision record in repo. **PENDING CLOUD DOC**
5. Define Qwen3-TTS ES-ES male documentary/cinematic acceptance rubric: naturalness, pronunciation, timestamps, stability, RAM/VRAM, generation time. **PENDING CLOUD DOC**
6. Prepare pronunciation lexicon/test script for astronomy terms. **PENDING CLOUD**
7. Real TTS A/B and performance measurement. **PC-ONLY**

## Workstream G — scientific/content regression assets

1. Preserve F57 cloud scenario evidence 8/8. **DONE**
2. Build review matrix mapping every scenario to science/visual/provenance/render/no-B-roll/recovery evidence. **PENDING CLOUD SUMMARY**
3. Preserve `INSUFFICIENT_MEDIA` as controlled fail/NEEDS_INPUT. **DONE CONTRACT / FINAL LOCAL PENDING**
4. Preserve `VISUAL_RECREATION` explicit labeling and non-real-observation semantics. **DONE CONTRACT / FINAL LOCAL PENDING**
5. Prepare first real post-freeze SOL_TO_MOON content brief using own-media corpus metadata already known, but do not fabricate unavailable local metadata. **PENDING CLOUD**
6. Current astronomical facts for that first production must be researched near production date from primary sources; do not freeze ephemeral ephemerides now unless the target date is fixed. **PENDING LATER**

## Workstream H — PR/issues/repository hygiene

1. PR #1 remains draft/open, no merge. **DONE/ONGOING**
2. PR #1 text records F57 8/8 and local certification requirement. **VERIFIED**
3. Issue #3 remains open for local/cloud reconciliation. **DONE**
4. Issue #4 retained as historical C2.11J Lunar checkpoint. **DONE**
5. Issue #5 remains canonical no-PC backlog. **DONE**
6. PR #2 remains demo-only WebUI draft. **DONE/ONGOING**
7. Do not modify main/productive branches merely to make the cloud dashboard look complete. **LOCKED**
8. Before PC return, create a final evidence/index document linking cloud checkpoints, open blockers and PC-only gates. **PENDING LAST CLOUD STEP**

## Workstream I — items that must NOT be falsely closed without PC

These remain intentionally open until 2026-09-09 or later:

1. actual local branch/head/stash/untracked preservation;
2. exact cloud↔local selective reconciliation;
3. fresh full local pytest;
4. real AstroMedia/catalog/media verification;
5. local F57 8/8 authority;
6. Qwen3-TTS real audio/timestamps/performance;
7. RTX 2060 GPU/VRAM evidence;
8. actual CUDA runtime-use evidence;
9. actual FFmpeg build/license;
10. real NVENC encode;
11. real libx264 fallback;
12. RAM/VRAM/OOM evidence;
13. full real Golden E2E;
14. human Review Studio acceptance;
15. real manual Publication Package;
16. final local OSS/SBOM fields;
17. F58 final evaluation;
18. explicit human freeze approval;
19. separately controlled V1 freeze;
20. first real production video.

## Proposed calendar

### 2026-08-30
- continuity documents, runner classification, OSS/SBOM baseline, Publication Package gap audit.

### 2026-08-31
- finish primary-source license verification for active V1 pipeline; service-vs-OSS classification.

### 2026-09-01
- Publication Package v0.2 planning contract + tests, no file writes/publication.

### 2026-09-02
- WebUI preview terminology/status refresh and mobile-safe review pass.

### 2026-09-03
- Qwen3.8 decision record + Qwen3-TTS acceptance/pronunciation test specification.

### 2026-09-04
- F57 8/8 evidence index and scenario review matrix.

### 2026-09-05
- SOL_TO_MOON first-production pre-brief using only already verified own-media facts; identify what must wait for real catalog/current ephemerides.

### 2026-09-06
- C3/F58 re-dispatch if runner execution has recovered; otherwise preserve blocker evidence once, no repeated blind retries.

### 2026-09-07
- repository/PR/issues consistency audit; update cloud readiness summary.

### 2026-09-08
- final pre-PC C3 checkpoint/backup; freeze cloud workstream; issue evidence index and next-session checklist.

### 2026-09-09
- execute `pc-return-playbook-2026-09-09.md` from preservation first.

## No-PC phase success criterion

By the night of 2026-09-08, every open item must be either:

- `CLOUD_DONE` with durable GitHub evidence;
- `CI_BLOCKED` with evidence that no product code was executed/failed; or
- `PC_ONLY` with an exact first-action checklist.

Nothing may remain merely undocumented or dependent on chat memory.
