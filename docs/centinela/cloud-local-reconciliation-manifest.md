# Cloud ↔ local reconciliation manifest

Date: 2026-08-30
Purpose: preserve the two non-interchangeable lineages until the Windows PC is available again on 2026-09-09.

## Non-negotiable status

- `BLIND_MERGE_FORBIDDEN=TRUE`
- `LOCAL_STATE_MUST_BE_PRESERVED_FIRST=TRUE`
- `CLOUD_PASS_IS_NOT_LOCAL_FINAL_AUTHORITY=TRUE`
- `MERGE_AUTHORIZED=FALSE`
- `AUTO_PUBLICATION=FALSE`
- `ARCHITECTURE_FREEZE_AUTHORIZED=FALSE`

## Local lineage to preserve first

Known local state from the last exact checkpoint:

- branch: `centinela-cert/golden-real-e2e-v0.1`
- HEAD: `186104539a7116ad48b96beac90eccd3c4c37801`
- stash: `22ee99b0703be803e63beaed2370485c84604c9a`
- stash message: `C2.11O-M V34 pre-V33 preserve 20260826-172847`
- known untracked files:
  - `app/services/centinela/quality/f57_real_runner.py`
  - `test/services/test_f57_real_runner.py`
  - `test/services/test_public_source_rights.py`
- expected V36 preservation evidence:
  - `V36_RESTORED_DIRTY_COUNT=3`
  - `V36_EXACT_ORIGINAL_STATUS_RESTORED=TRUE`
  - `V36_ORIGINAL_PRE_V33_STATE_RESTORED=TRUE`
  - `V36_STASH_WAS_APPLIED_NOT_POPPED=TRUE`

Important: local commit `186104...` was not present remotely byte-identical at the last verification. This must be rechecked, not assumed changed.

## Cloud lineage

Current certified cloud work is represented by:

- working/certification branch: `centinela-cert/cloud-mobile-v0.1`
- F57 cloud checkpoint recorded by PR #1: `a88f08f...`
- immutable-by-project-convention recovery branch: `centinela-backup/cloud-f57-8of8-20260830`
- F57 cloud status: `8/8 PASS`
- C3/F58 branch: `centinela-cert/c3-f58-readiness-v0.1`
- C3/F58 branch entered this no-PC phase from commit `5a9a2fa31dd13fdc04ef9626b9486480e9d246f5`; later documentation-only commits are expected during the no-PC phase.

## Cloud achievements that may be candidates for selective port

Do not port mechanically. Compare implementation and tests first.

1. C2.11J media specificity/fail-closed grounding.
2. deterministic FactLock-only scientific visuals.
3. Lunar cloud MEDIA 5/5.
4. F57 cloud scenario certification 8/8.
5. Linux/Windows hermetic path handling used by cloud scenario workflows.
6. C3/F58 readiness mechanism and guardrails.
7. no-PC documentation/evidence produced after 2026-08-30.

## Known exclusions / unsafe historical material

- V32 localization alias Luna→moon as strong object-overlap evidence: `DO_NOT_PORT / DO_NOT_RUN`.
- V33 local result: not certified; historical failure was `ModuleNotFoundError: app` due replay outside repo root.
- Any remote state must not overwrite the three local untracked files before they are preserved.
- No force push, `git reset --hard`, `git clean -fd`, or stash deletion.

## Reconciliation algorithm for 2026-09-09

### Phase A — preserve exact local source of truth

1. Verify current branch and HEAD without modifying anything.
2. Record `git status --short` and full status.
3. Verify stash list and the exact stash object.
4. Verify the three untracked files exist and hash them.
5. Create an external/local backup of the three untracked files.
6. Create a dedicated Git branch/commit preserving the local lineage only after the dirty/untracked state has been independently backed up.
7. Push that preservation branch if network is available.

### Phase B — compare, do not merge

8. Fetch remote refs.
9. Compare local preserved commit/branch with cloud backup/checkpoint and C3 branch.
10. Produce changed-file inventory grouped as:
   - local-only;
   - cloud-only;
   - both changed;
   - identical;
   - generated/evidence-only.
11. For every both-changed production file, compare tests and behavioral contracts before selecting a side.

### Phase C — selective reconciliation

12. Port cloud changes in small logical batches.
13. After each batch: compile/lint where applicable + targeted tests.
14. Preserve FactLock numeric integrity, MaterialSelector final authority, rights/provenance gates and publication guardrails.
15. Never use an alias to bypass missing structured astronomy grounding.

### Phase D — certification after reconciliation

16. Full pytest.
17. Real AstroMedia/material replay.
18. Local F57 scenarios.
19. Qwen3-TTS runtime/voice.
20. RTX/CUDA/VRAM/RAM checks.
21. NVENC smoke + quality comparison.
22. libx264 fallback.
23. full real Golden E2E.
24. human Review Studio.
25. real Publication Package.
26. final OSS audit and F58.
27. human freeze approval only after every blocking check is green.

## Stop conditions

Stop reconciliation and classify the discrepancy if any of the following occurs:

- local HEAD differs unexpectedly from `186104...`;
- stash object/message is missing or altered;
- one of the three untracked files is missing before preservation;
- cloud/local behavior conflicts on FactLock, rights, MaterialSelector authority or publication safety;
- tests must be weakened to make a port pass;
- any proposed operation would destroy an unrecoverable local state.
