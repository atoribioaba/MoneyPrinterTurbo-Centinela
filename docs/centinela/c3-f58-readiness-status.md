# C3 / F58 Readiness Status

Date: 2026-08-30
Branch: `centinela-cert/c3-f58-readiness-v0.1`

## Executive state

- `F57_CLOUD=8/8_PASS`
- `F57_LOCAL=PENDING_PC`
- `LOCAL_HARDWARE_CERTIFICATION=PENDING_PC`
- `F58_MECHANISM_CLOUD=PASS`
- `F58_EXECUTABLE_MATRIX=3/3_PASS`
- `ANALYTICS_ADAPTER_MECHANISM=PASS`
- `REAL_CHANNEL_ANALYTICS_REQUIRED_FOR_V1=FALSE`
- `SBOM_PROVISIONAL_CLOUD=PASS`
- `PUBLIC_REPO_SECRET_AUDIT=PASS`
- `OSS_AUDIT_CLOUD=ADVANCED_LOCAL_FINAL_FIELDS_PENDING`
- `HUMAN_FREEZE_APPROVAL=FALSE`
- `ARCHITECTURE_FREEZE_AUTHORIZED=FALSE`
- `AUTO_PUBLICATION=FALSE`

The F58 mechanism is intentionally audit-only. It may authorize a freeze only after every blocking technical gate and explicit human approval, and it must never execute the freeze itself.

## F58 gate matrix

| Gate | Current state | Blocking | Can close without PC? | Evidence / next action |
|---|---|---:|---:|---|
| Operational hardening not blocked | PENDING_LOCAL_RECHECK | Yes | Partially | Cloud mechanism is executable; workstation state must be revalidated on return. |
| Golden real E2E certified | PENDING_PC | Yes | No | Requires real local media/runtime/hardware path and human-review stop. |
| Manual Publication Package ready | PENDING_REAL_GOLDEN | Yes | Mechanism mostly | v0.2 cloud contract exists; real package depends on approved Golden output. |
| Analytics adapter operational | CLOUD_PASS | Yes | Yes | Dedicated 3-platform mechanism gate passed; real channel data is not required for V1 mechanism readiness. |
| OSS audit complete and verified | ADVANCED_LOCAL_FINAL_FIELDS_PENDING | Yes | Mostly | Cloud/static licenses plus transitive SBOM exist; local FFmpeg/NVENC/runtime/model fields remain pending. |
| Human freeze approval | NOT_GRANTED | Final | No automation | Must be explicit and only after technical readiness. |

## F58 mechanism CI — certified and revalidated in cloud

Historical pre-step/no-runner failures were resolved after repository visibility became public. The exact hidden private-repository billing/eligibility cause was not directly observed and is not asserted.

Initial final mechanism certification:

- workflow: `.github/workflows/centinela-c3-f58-readiness.yml`
- run: `33331257171`
- source commit: `208ed4c4c02178681202e9a73e6c3fbbe1a0fe1d`
- Linux / Python 3.11: PASS
- Linux / Python 3.13: PASS
- Windows / Python 3.11: PASS
- Linux 3.11 focal Ruff: PASS
- F58 contract tests: PASS
- semantic freeze guard: PASS

During executable CI recovery two genuine CI-quality defects were found and fixed without weakening readiness semantics:

1. Ruff violations in the compact F58 source surface;
2. a formatting-dependent textual freeze guard, replaced with semantic Pydantic/default checks.

After hardening the Analytics gate so it no longer uses literal `passed=True`, F58 was revalidated:

- run: `33332112652`
- Linux / Python 3.11: PASS including Ruff, contract and semantic freeze guard
- Linux / Python 3.13: PASS including contract and semantic freeze guard
- Windows / Python 3.11: PASS including contract

`F58_MECHANISM_CLOUD=PASS` certifies the mechanism only. It does not convert missing local/Golden/human evidence into readiness.

## Analytics Adapter mechanism — cloud PASS

Dedicated workflow:

- `.github/workflows/centinela-c3-analytics-adapter.yml`
- run: `33332179491`
- source commit: `f5e0159404d2a90c8f941eef4abd5302279b5178`
- Linux / Python 3.11: PASS
- Linux / Python 3.13: PASS
- Windows / Python 3.11: PASS
- Linux 3.11 focal Ruff: PASS
- targeted Analytics + API + F58 tests: `24 passed`
- semantic side-effect guard: PASS

The adapter now proves:

- deterministic CSV/JSON ingestion;
- explicit timezone required for `observed_at_utc`;
- offset timestamps normalized to UTC;
- invalid JSON/shapes/metrics/timestamps fail closed;
- missing data yields `WAITING_FOR_IMPORT_DATA`, not a false production-ready state;
- a failed parse does not poison the next valid import;
- API invalid input returns HTTP 422;
- `network_calls=0`;
- `api_calls=0`;
- `database_writes=0`;
- `credentials_required=false`;
- `uses_llm=false`;
- `auto_publication=false`.

F58 now evaluates Analytics operational readiness from those mechanism guardrails and a non-empty evidence hash instead of hard-coding the gate to pass. `WAITING_FOR_IMPORT_DATA` is valid for mechanism certification, therefore:

- `ANALYTICS_ADAPTER_MECHANISM=PASS`
- `REAL_CHANNEL_ANALYTICS_REQUIRED_FOR_V1=FALSE`
- `ANALYTICS_REAL_DATA=PENDING_NOT_BLOCKING_MECHANISM`
- `ANALYTICS_PERSISTENCE_OUT_OF_SCOPE_ADAPTER_V0_1=TRUE`

The last line is intentional: adapter v0.1 is an import/normalization boundary and explicitly performs no database writes. Actual analytics storage/persistence is a separate concern and is not falsely claimed as certified here.

## Provisional transitive SBOM — cloud PASS

Run `33331798267` successfully resolved the checked-in `uv.lock` on Linux / Python 3.11 and generated a validated reproducible CycloneDX 1.6 JSON SBOM with license-text gathering.

- source commit: `994cf178122c3bdbfb538e88096e33624381d0e9`
- resolved packages: `119`
- `uv sync --frozen`: PASS
- `cyclonedx-bom==7.3.1`
- `C3_SBOM_STRUCTURE=PASS`
- artifact: `centinela-c3-python-sbom-33331798267`
- artifact id: `9737853863`

Evidence hashes:

- `pyproject.toml`: `10815c8f8b857c9037764992ea663a08d7c8ea5663caa02ba971dbe28cb1afea`
- `uv.lock`: `ad161c3b46f2598f01b2265128a3ebbf14e2fa2ce77d64712cf0af4a606aed83`
- CycloneDX JSON: `730cf88f862339b994b4b8507b02fe455c975bf3a7978983d83f89cf84969782`
- resolved inventory: `f1523b2748b38df44db063d635c04e5eec4ce5facb3ed3e174cb2a931f0bce01`

This does not replace the final Windows-installed/runtime SBOM.

## Public repository security gate

After visibility became public, Gitleaks 8.30.1 was executed with full redaction over all fetched branches/tags plus the current tree.

Run `33331706938`:

- commits scanned: `916`
- history findings: `0`
- current-tree findings: `0`
- raw reports uploaded: no
- secret values persisted by the audit: no

`.gitignore` was then hardened for common local secret material.

`PUBLIC_REPO_SECRET_AUDIT=PASS`

## Status semantics

Until all blocking technical gates are genuinely green, expected F58 final state remains:

`NOT_READY_FOR_ARCHITECTURE_FREEZE`

When all technical gates are green but no human approval exists:

`READY_FOR_HUMAN_FREEZE_APPROVAL`

Only after explicit human approval may F58 report:

`ARCHITECTURE_FREEZE_AUTHORIZED`

Even then:

- `architecture_v1_frozen=false`
- `freeze_executed=false`
- `auto_publication=false`
- `auto_activation=false`
- `writes_runtime_config=false`
