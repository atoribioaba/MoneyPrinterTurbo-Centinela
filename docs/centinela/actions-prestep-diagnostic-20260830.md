# GitHub Actions pre-step diagnostic — 2026-08-30

Status: `CONTROL_PLANE_BLOCKER_RESOLVED`

This record preserves both the original no-runner failure and the verified recovery. It does **not** invent a private-repository billing/quota root cause that was never directly observed.

## 1. Original failure — verified

Dedicated F58 run `33323286894`, attempt 2, failed before step execution for:

- Linux / Python 3.11
- Linux / Python 3.13
- Windows / Python 3.11

Raw job metadata showed for all three jobs:

- `status=completed`
- `conclusion=failure`
- `steps=[]`
- `runner_id=0`
- `runner_name=""`
- `runner_group_id=0`
- `runner_group_name=""`

A minimal independent probe then reproduced the same condition:

- branch: `centinela-diagnostics/actions-prestep-probe-20260830`
- commit: `4fb3de881da9b8d4692387f34b4f8268a8e63aa4`
- workflow: `Centinela Actions Pre-step Probe`
- run: `33325885812`
- workload: `ubuntu-latest` plus one intended shell step only
- no checkout, Python, uv, dependencies, project imports, secrets or product code
- result before recovery: failure with no runner assignment / no step execution

This proved the original failure was outside F58/MoneyPrinterTurbo/Centinela product execution.

## 2. Visibility change and recovery — verified sequence

The repository was subsequently changed from private to public on 2026-08-30.

GitHub repository metadata was re-read and confirmed:

- `visibility=public`
- `archived=false`
- owner permission remains `admin`

No claim is made that a specific private-repository billing field was the hidden root cause because Billing/Usage/Budgets were not directly available through the connector.

Immediately after public visibility was confirmed, the minimal probe was re-run exactly once, following the recovery protocol.

Recovery result for run `33325885812`:

- runner allocated successfully;
- `Set up job` executed;
- `Runner entered step execution` executed;
- `Complete job` executed;
- conclusion: `success`.

Therefore:

- `CONTROL_PLANE_BLOCKER_RESOLVED=TRUE`
- `RUNNER_ALLOCATION_RECOVERED=TRUE`
- `CENTINELA_ACTIONS_STEP_EXECUTION=PASS`

The public-visibility change is the operational recovery boundary observed in this project. The exact hidden private-repository eligibility/billing condition remains `NO_VERIFICADO` and is no longer required for the current public-repository workflow path.

## 3. F58 executable mechanism after recovery

F58 was then executed on real GitHub-hosted runners.

Initial executable run exposed two genuine CI-quality defects rather than product-readiness failures:

1. Linux 3.11 Ruff violations in the compact F58 source surface;
2. a brittle textual `grep` freeze guard that depended on source formatting rather than semantics.

These were corrected without weakening F58 readiness semantics:

- F58 files were mechanically normalized for Ruff;
- the freeze guard was replaced by a Python semantic check against Pydantic defaults and required gate identifiers.

Final F58 mechanism run:

- run: `33331257171`
- source commit: `208ed4c4c02178681202e9a73e6c3fbbe1a0fe1d`
- Linux / Python 3.11: `success`
- Linux / Python 3.13: `success`
- Windows / Python 3.11: `success`

Linux 3.11 additionally passed focal Ruff. The semantic freeze guard passed and verifies, among other invariants:

- `architecture_v1_frozen=false`
- `freeze_executed=false`
- `auto_publication=false`
- `auto_activation=false`
- `writes_runtime_config=false`
- `human_freeze_approval=false` by default
- required gates for Golden real E2E, manual Publication Package, analytics adapter and OSS audit remain present.

Therefore:

- `F58_MECHANISM_CLOUD=PASS`
- `F58_EXECUTABLE_MATRIX=3/3_PASS`
- `F58_FINAL_READINESS=NOT_READY_FOR_ARCHITECTURE_FREEZE`

The last line is intentional: mechanism certification does not satisfy the remaining real/local/human gates.

## 4. C3 SBOM after recovery

Prepared CycloneDX execution was also run successfully after runner recovery.

Run:

- workflow: `Centinela C3 Python SBOM`
- run: `33331798267`
- source commit: `994cf178122c3bdbfb538e88096e33624381d0e9`
- Python: 3.11
- resolved package count: `119`
- `uv sync --frozen`: PASS
- CycloneDX generator: `cyclonedx-bom==7.3.1`
- CycloneDX spec: `1.6`
- validation: PASS
- reproducible output mode: enabled
- license-text gathering: enabled
- `C3_SBOM_STRUCTURE=PASS`

Evidence hashes:

- `pyproject.toml`: `10815c8f8b857c9037764992ea663a08d7c8ea5663caa02ba971dbe28cb1afea`
- `uv.lock`: `ad161c3b46f2598f01b2265128a3ebbf14e2fa2ce77d64712cf0af4a606aed83`
- `centinela-python-sbom.cdx.json`: `730cf88f862339b994b4b8507b02fe455c975bf3a7978983d83f89cf84969782`
- `centinela-python-inventory.json`: `f1523b2748b38df44db063d635c04e5eec4ce5facb3ed3e174cb2a931f0bce01`

Artifact:

- `centinela-c3-python-sbom-33331798267`
- artifact id: `9737853863`

This is authoritative cloud/Linux evidence for the checked-in lockfile, not the final Windows-installed SBOM.

## 5. Public-repository secret audit

Because repository visibility became public, a fail-closed secret audit was added immediately.

Workflow:

- `Centinela Public Secret Audit`
- run: `33331706938`
- source commit: `eeb8493f63b6d70c767a1d0c8f720fb83cb99357`
- Gitleaks: `8.30.1`
- official Linux x64 archive SHA-256 verified before execution
- permissions: `contents: read`
- checkout credentials not persisted
- all branches/tags fetched for history coverage
- commits scanned: `916`
- full Git-history findings: `0`
- current-tree findings: `0`
- secret values emitted/persisted by the audit: `false`
- raw finding reports uploaded: `false`

Only the redacted summary was uploaded.

`.gitignore` was subsequently hardened to ignore common machine-local secret material such as `.env*`, private-key containers and local credential files, while permitting explicitly named example/template files.

Therefore:

- `PUBLIC_REPO_SECRET_AUDIT=PASS`
- `GITLEAKS_HISTORY_FINDINGS=0`
- `GITLEAKS_CURRENT_TREE_FINDINGS=0`

GitHub's own secret-scanning-alert endpoint was not exposed by the connector and is therefore not claimed as independently checked.

## 6. Current classification

The historical classification remains useful for forensic continuity:

- `CI_PRE_STEP_EXECUTION_BLOCKER / CONTROL_PLANE` — historical, resolved.

Current state:

- `ACTIONS_STEP_EXECUTION=PASS`
- `CONTROL_PLANE_BLOCKER_RESOLVED=TRUE`
- `F58_MECHANISM_CLOUD=PASS`
- `SBOM_PROVISIONAL_CLOUD=PASS`
- `PUBLIC_REPO_SECRET_AUDIT=PASS`
- `F58_APPLICATION_REGRESSION=FALSE_ON_CERTIFIED_MECHANISM_RUN`
- `BLIND_RERUN_LOOP=FALSE`

Still required locally/finally:

- exact Windows installed/runtime SBOM;
- real FFmpeg build/license mode;
- RTX/CUDA/NVENC evidence;
- real AstroMedia/media path;
- real Golden E2E;
- human review;
- real manual Publication Package;
- final OSS audit fields;
- final F58 readiness evaluation;
- explicit human freeze approval.

Guardrails remain:

- `LOCAL_CERTIFICATION_REQUIRED=TRUE`
- `MERGE_AUTHORIZED=FALSE`
- `AUTO_PUBLICATION=FALSE`
- `ARCHITECTURE_FREEZE_AUTHORIZED=FALSE`
