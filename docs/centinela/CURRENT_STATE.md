# EL CENTINELA DEL UNIVERSO — CURRENT STATE

Canonical status index for MoneyPrinterTurbo-Centinela.

Last consolidated: 2026-09-01  
Authority: the PR #6 head commit containing this file.  
Audited parent baseline: `8eff3a3bcbffccaf4ccb133835e852dedb6a47d5`.

This file is an index of the current state. Historical certificates remain immutable evidence and are not rewritten when later evidence supersedes their status statements.

## 1. CURRENT — non-negotiable invariants

```text
AUTO_PUBLICATION=FALSE
APPROVED != AUTHORIZED_TO_PUBLISH
AUTHORIZATION_TO_PUBLISH=FALSE
ARCHITECTURE_FREEZE_AUTHORIZED=FALSE
REAL_HUMAN_REVIEW=PENDING_LOCAL
PR_6=OPEN_DRAFT_UNMERGED
```

Canonical production policy:

```text
GENERAR -> REVISAR -> APROBAR -> PUBLICAR
```

Canonical pipeline:

```text
TEMA
-> INVESTIGACION
-> FACT LOCK
-> WRITER ROOM
-> GUION
-> ESCENAS
-> MEDIA
-> SMARTFOCAL/REFRAMING
-> VOZ
-> SUBTITULOS
-> AUDIO
-> VIDEO_BASE
-> REVIEW
-> PUBLICATION PACKAGE
```

Publication is a manual boundary outside automatic production authority.

## 2. CURRENT — remote safety hardening

### Automatic publication

The Centinela profile treats automatic publication as a code invariant, not as a user-configurable permission.

- `app.services.upload_post.AUTO_PUBLICATION` is `False`.
- `UploadPostService.auto_upload` is fail-closed and does not trust legacy `upload_post_auto_upload=true` configuration.
- The legacy task pipeline still requires `upload_post_service.auto_upload` before it can schedule cross-post work, so automatic cross-post cannot be enabled by legacy configuration.
- Explicit/manual upload capability is not equivalent to automatic publication authority.

### API bind

The Centinela configuration package forces the effective API bind host to:

```text
127.0.0.1
```

This remains true even when a pre-existing legacy `config.toml` contains `listen_host = "0.0.0.0"`.

### Human review UI

The active Review surface is the structured seven-gate `HumanFinalReviewRecord` flow. Package-level resolution of the legacy `pages.review_page` symbol is redirected to the structured Review implementation.

Legacy boolean approval is not authoritative.

## 3. CURRENT — cloud-certified authority boundaries

The audited parent baseline `8eff3a3bcbffccaf4ccb133835e852dedb6a47d5` completed the unified cloud gate successfully:

```text
GENERAL_CI=3/3_PASS
PROTECTED_TARGETS=3/3_PASS
REVIEW_GATE=3/3_PASS
STATE_MACHINE_AUDIT=FORMALLY_CLOSED
LEGACY_REVIEW_BYPASS_CLOSED=TRUE
```

General CI baseline evidence included:

```text
GLOBAL_RUFF=PASS
PYTEST=1572 passed, 12 skipped
SUBTESTS=4551 passed
COVERAGE=77%
FAIL_UNDER=70
```

The commit containing this file must obtain its own same-SHA CI evidence before the remote-hardening delta is considered certified.

## 4. CURRENT — State Machine and Review authority

Protected public authority remains:

```text
ProjectStateMachine -> ProtectedProjectStateMachine
ProductionSpine -> hardened review-gate ProductionSpine
```

Only a durable structured human-review record with all seven canonical gates passing can authorize the transition to `FINAL_APPROVED`.

Canonical review gates:

1. science;
2. visual;
3. audio;
4. subtitles;
5. rights;
6. thumbnail;
7. copy.

A boolean `approved=True`, legacy metadata, a forged structured record, or an older approval followed by a newer adverse review must not become authoritative.

## 5. CURRENT — Writer Room / Fact Lock

Writer Room remains local-first and isolated from remote LLM authority:

```text
DEFAULT_RUNTIME=OLLAMA_LOOPBACK
DEFAULT_ENDPOINT=http://127.0.0.1:11434
MODEL_AUTO_DOWNLOAD=FALSE
FACTLOCK_REQUIRED=TRUE
STRUCTURED_OUTPUT=TRUE
```

The deterministic quantitative Fact Lock guard is part of the productive Writer Room path and the baseline full CI executed its regression tests.

Current limitation remains deliberate:

```text
FULL_NATURAL_LANGUAGE_SEMANTIC_PROOF=FALSE
HUMAN_SCIENCE_REVIEW_REQUIRED=TRUE
```

## 6. CURRENT — Scientific Visuals

Current static/deterministic contract includes:

```text
OUTPUT=1080x1920_PNG
NETWORK_CALLS=0
AI_GENERATED=FALSE
FACTLOCK_ONLY=TRUE
CONTENT_SHA256=TRUE
UNSUPPORTED_FACT=FAIL_CLOSED
SAME_ENVIRONMENT_RERENDER_BYTE_STABLE=TESTED
```

Cross-platform Windows/Linux byte-identical rendering is not yet a certified invariant.

## 7. SUPERSEDED — historical status statements

The following documents remain valid historical evidence but contain status statements superseded by later evidence.

| Document | Historical statement | Current interpretation |
|---|---|---|
| `c3-factlock-adversarial-certification.md` | `PYTEST_EXECUTED=FALSE`, Actions pre-step blocker | `SUPERSEDED`: the Fact Lock regression files were later executed inside successful full General CI on baseline `8eff3a3...` |
| `actions-prestep-diagnostic-20260830.md` and related control-plane notes | Actions could not reach first executable step | `SUPERSEDED/HISTORICAL`: later C3 workflows obtained runners and completed real steps; recovery root cause remains `NOT_VERIFIED` |
| earlier Review Gate run references in `review-state-machine-hardening-c3.md` | earlier focused certification SHA/run | `SUPERSEDED_BY_LATER_SAME_SHA_UNIFIED_GATE` for current status; mechanism history remains valid |
| earlier cloud checkpoints | intermediate readiness percentages/states | `HISTORICAL`; use this file plus current CI for current status |

`SUPERSEDED` does not mean evidence should be deleted.

## 8. DIVERGED_CANDIDATE — not canonical

Branch:

```text
centinela-cert/c3-factlock-adversarial-v0.1
```

contains one commit not present in the current PR #6 lineage:

```text
59cded452362f1c153ff165c01bbc4ecc82c49ff
fix(c3): make FactLock semantically self-verifying
```

That commit adds model-level validation tying `FactLock.context_hash` to canonical facts/source IDs and strengthens source/fact uniqueness checks.

Classification:

```text
FACTLOCK_SEMANTIC_SELF_VERIFY_COMMIT=DIVERGED_CANDIDATE
CANONICAL=FALSE
AUTO_MERGE=FALSE
SEPARATE_REVIEW_AND_CERTIFICATION_REQUIRED=TRUE
```

It must not be silently cherry-picked into the canonical line without its own compatibility review and regression evidence.

## 9. Branch and tag interpretation

At the audited parent baseline:

- `main` is an ancestor of the PR #6 head; PR head was 306 commits ahead and 0 behind.
- PR base `centinela-cert/c3-f58-readiness-v0.1` is an ancestor of PR #6 head; head was 36 commits ahead and 0 behind.
- remote branch `centinela-local` is an ancestor of PR #6 head; remote head was 305 commits ahead and 0 behind. This says nothing about unpushed files or stashes on the physical PC.
- the Fact Lock adversarial branch above is genuinely diverged by one unique commit.
- repository release tags `v1.1.0` through `v1.3.4` belong to historical upstream/release lineage; `main` is later than `v1.3.4`, and Centinela C3 development is later still.

Historical feature, backup, diagnostic and certification branches are evidence/history, not automatic sources of authority.

## 10. PENDING_LOCAL — do not certify from cloud

The following require the physical Windows workstation, real hardware, real media or real human judgement:

```text
PC_PRESERVATION_AND_RECONCILIATION=PENDING_LOCAL
E_DRIVE_MEDIA_TYPE_VERIFICATION=PENDING_LOCAL
RTX_2060_RUNTIME=PENDING_LOCAL
CUDA_ACTUAL_EXECUTION=PENDING_LOCAL
NVENC_REAL_ENCODE=PENDING_LOCAL
LIBX264_FALLBACK_COMPARISON=PENDING_LOCAL
QWEN3_TTS_ES_ES_REAL=PENDING_LOCAL
WHISPER_OR_TTS_TIMESTAMP_REAL_VALIDATION=PENDING_LOCAL
ASTROMEDIA_REAL_CATALOG=PENDING_LOCAL
F57_LOCAL_REAL=PENDING_LOCAL
GOLDEN_REAL_E2E=PENDING_LOCAL
SCIENTIFIC_VISUALS_CROSS_PLATFORM_HASH=PENDING_LOCAL
REAL_HUMAN_REVIEW=PENDING_LOCAL
REAL_PUBLICATION_PACKAGE=PENDING_LOCAL
FREEZE_V1=PENDING_AUTHORIZATION
```

No cloud fixture may be substituted for those certifications.

## 11. PENDING_LOCAL / maintenance quality

Static audit areas that should be revisited locally after preservation/reconciliation:

- explain every current pytest skip with `pytest -rs`;
- full Windows pytest/coverage, not only the General CI smoke subset;
- increase coverage around AV render/audio/video surfaces and Fact Lock guard edges;
- exhaustive filesystem search for `TODO`, `FIXME`, `NotImplemented`, placeholder/stub implementations and dead code because GitHub code-search indexing returned incomplete results;
- validate Windows path, Unicode and long-path behavior;
- reconcile Docker dependency input with the canonical `uv.lock` environment before selecting Docker as V1 architecture;
- pin/record the `uv` tool version for reproducibility;
- consider immutable commit-SHA pinning for critical GitHub Actions after compatibility review.

## 12. Supply-chain state

Current workflow permissions are generally least-privilege for certification workflows, but action dependencies are referenced by release tags such as:

```text
actions/checkout@v4
actions/setup-python@v5
astral-sh/setup-uv@v6
actions/upload-artifact@v4
```

Classification:

```text
CURRENT_CI_SUPPLY_CHAIN=FUNCTIONAL
ACTION_SHA_PINNING=OPTIONAL_HARDENING_PENDING
UV_TOOL_VERSION_PIN=OPTIONAL_HARDENING_PENDING
```

Do not change these during a safety-boundary patch without separate certification.

## 13. Architecture status

No architecture freeze is authorized.

Known static packaging concern:

```text
DOCKER_DEPENDENCY_PARITY=INCOMPLETE
```

The Docker build path uses `requirements.txt`, while the canonical C3 CI path uses `uv sync --frozen` from `pyproject.toml`/`uv.lock`; later Centinela dependencies are not guaranteed to be represented identically in the legacy requirements path.

Therefore:

```text
WINDOWS_NATIVE_GIT_UV=CANDIDATE
DOCKER_WSL2=CANDIDATE
FINAL_ARCHITECTURE=NOT_FROZEN
```

## 14. Safety footer

```text
AUTO_PUBLICATION=FALSE
AUTHORIZATION_TO_PUBLISH=FALSE
APPROVED_NE_AUTHORIZED_TO_PUBLISH=TRUE
ARCHITECTURE_FREEZE_AUTHORIZED=FALSE
REAL_HUMAN_REVIEW=PENDING_LOCAL
DO_NOT_MERGE_FROM_THIS_DOCUMENT=TRUE
DO_NOT_PUBLISH_FROM_THIS_DOCUMENT=TRUE
```
