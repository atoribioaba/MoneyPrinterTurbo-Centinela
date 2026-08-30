# C3 — Publication Security + State Boundary Audit

Status: **PASS (cloud mechanism)**  
Scope: authority boundaries from ProductionOrchestrator through VideoBaseE2E, FinalizationE2E and PublicationPackage.  
This document does **not** certify real local renders, real human review, local NVENC/CUDA, real Publication Package files, or authorization to publish.

## Canonical safety boundary

```text
ProductionOrchestrator
  -> VideoBaseE2E
  -> FinalizationE2E
  -> PublicationPackage
  -> explicit manual publication decision outside this mechanism
```

`APPROVED != AUTHORIZED_TO_PUBLISH`.

The mechanism is fail-closed and keeps all publication side effects disabled:

- `auto_publication = false`
- `authorization_to_publish = false`
- `uploads_files = false`
- `network_calls = 0`
- `webhook_calls = 0`
- `marks_published = false`
- `local_final_certification_required = true`

## Bypass found and closed — ProductionOrchestrator

The active `/production-orchestrator/plan` API previously accepted declarative downstream progress through `human_review_state=APPROVED`, `finalization_complete=true`, and `publication_package_complete=true` without binding that progression to the seven-dimension human-review evidence used by FinalizationE2E.

C3 hardening changed ProductionOrchestrator to v0.2 and preserves the pipeline dependency direction. It now:

1. rejects declarative `APPROVED`;
2. rejects declarative `finalization_complete=true`;
3. rejects declarative `publication_package_complete=true`;
4. rejects construction of downstream-only orchestrator states such as `READY_FOR_FINALIZATION`, `READY_FOR_PUBLICATION_PACKAGE`, and `COMPLETE`;
5. stops at the downstream review boundary after a VIDEO_BASE manifest is present;
6. delegates authoritative human approval to FinalizationE2E and publication-package readiness to PublicationPackage;
7. performs no render, network, upload, webhook, publication authorization, or published-state mutation.

An initial implementation attempt that imported Finalization/Publication models upstream was rejected during the audit because `VideoBaseE2E` already depends on `ProductionOrchestratorPlan`; keeping that design would create a cyclic dependency. The corrected architecture retains the one-way dependency shown above.

## FinalizationE2E v0.2 hardening

`FINALIZATION_E2E_PASS` now requires all of the following as model-level invariants, not merely service-generated conventions:

### Human review evidence

- `human_review_approved`
- `review_science`
- `review_visual`
- `review_audio`
- `review_subtitles`
- `review_rights`
- `review_thumbnail`
- `review_copy`

All eight canonical checks must exist and pass.

### Final render evidence

Required profiles:

- `MASTER_VERTICAL_2160X3840`
- `SOCIAL_VERTICAL_1080X1920`

Required canonical checks:

- master/social presence;
- master/social file existence;
- master/social SHA-256;
- canonical resolution (2160x3840 master; 1080x1920 social);
- 30 fps tolerance;
- at least one audio stream;
- subtitles ready;
- publication rights ready.

Both required artifacts are validated directly by the model. Missing/invalid SHA-256, duplicate/missing profiles, wrong resolution/fps, missing audio/subtitles, or missing publication rights prevent `FINALIZATION_E2E_PASS`.

## PublicationPackage trust-boundary hardening

`PublicationPackageRequest` revalidates the complete serialized `FinalizationE2EPlan` before accepting it as package evidence. This closes the internal Pydantic `model_copy(update=...)` mutation path, which otherwise can produce an already-constructed nested model without rerunning validation.

Negative regressions cover mutated/fabricated evidence including:

- missing video SHA-256;
- publication rights changed to false;
- `human_review_recorded=false`;
- missing `review_science`;
- declarative downstream orchestrator completion;
- fabricated downstream orchestrator status;
- finalization PASS with review evidence but no canonical final renders.

PublicationPackage v0.2 remains planning/manual-only and requires the canonical 8-asset package with hashes before `READY_FOR_MANUAL_PACKAGE`.

## GitHub Actions evidence

Workflow: `.github/workflows/centinela-c3-security-state-machine.yml`

### Run 33338742736 — diagnostic first pass

- Windows / Python 3.11: contract PASS
- Linux / Python 3.13: contract PASS
- Linux / Python 3.11: Ruff failed before pytest because the first lint scope included pre-existing compressed-style code in legacy `video_base_e2e.py`.
- Classification: historical/focal lint-scope issue, not functional security/state failure.

### Run 33338846538 — corrected lint scope

- Head: `84f8387653a80f0055f39626c6c4ce997d9e4fbc`
- Workflow conclusion: **SUCCESS**
- Matrix: Linux 3.11 / Linux 3.13 / Windows 3.11.

### Run 33339040168 — final hardened contract

- Head: `8b4666eec292065ff0591ba1c40466d405d8777c`
- Workflow conclusion: **SUCCESS**
- Linux / Python 3.11: compile PASS, focal Ruff PASS, security/state pytest contract PASS, artifact upload PASS.
- Linux / Python 3.13: compile PASS, security/state pytest contract PASS, artifact upload PASS.
- Windows / Python 3.11: compile PASS, security/state pytest contract PASS, artifact upload PASS.

JUnit artifacts:

| Platform | Artifact | Digest |
|---|---|---|
| Linux 3.11 | `security-state-ubuntu-latest-3.11-33339040168` | `sha256:aedf4c4b70de5f06598b4e32748484e411d855416e5ffb24f61efdb302a0595a` |
| Linux 3.13 | `security-state-ubuntu-latest-3.13-33339040168` | `sha256:ae4867f107fcd60910c059234754b89cd2b3ba921b4586daec173e2c239d416e` |
| Windows 3.11 | `security-state-windows-latest-3.11-33339040168` | `sha256:32f08b2fa1bf0c7faddc7bc20ddd3d3fa91a35c487f8c99e3601b9330fa0ae7a` |

Artifacts expire according to the GitHub Actions retention policy; the run IDs, commit SHAs, workflow definition, and this audit remain the durable evidence index.

## Actions infrastructure status

The earlier C3 `CI_PRE_STEP_EXECUTION_BLOCKER / CONTROL_PLANE` is **not reproduced by these current runs**. Multiple jobs obtained real runners and executed checkout, Python setup, uv sync, compile, pytest, artifact upload, and focal Ruff where configured.

Current classification:

```text
ACTIONS_STEP_EXECUTION = PASS_ON_CURRENT_C3_RUNS
CI_PRE_STEP_EXECUTION_BLOCKER = HISTORICAL / NOT_REPRODUCED_NOW
ROOT_CAUSE_OF_RECOVERY = NOT_VERIFIED
```

Do not infer the historical root cause from the recovery.

## Gate result

```text
PUBLICATION_SECURITY_CLOUD = PASS
STATE_BOUNDARY_CLOUD = PASS
PRODUCTION_ORCHESTRATOR_BYPASS = CLOSED
FINALIZATION_E2E_V0_2_CLOUD = PASS
PUBLICATION_PACKAGE_V0_2_CLOUD = PASS
AUTO_PUBLICATION = FALSE
AUTHORIZATION_TO_PUBLISH = FALSE
MARKS_PUBLISHED = FALSE

REAL_HUMAN_REVIEW = PENDING_LOCAL
REAL_FINAL_RENDERS = PENDING_LOCAL
REAL_PUBLICATION_PACKAGE = PENDING_LOCAL
LOCAL_FINAL_CERTIFICATION_REQUIRED = TRUE
```

This gate does not authorize publication and does not execute Freeze V1.
