# GitHub Actions pre-step diagnostic — 2026-08-30

Status: `CONTROL_PLANE_BLOCKER_CONFIRMED`

This diagnostic exists to separate MoneyPrinterTurbo/Centinela failures from GitHub Actions execution-plane failures.

## F58 evidence

Dedicated F58 run `33323286894` failed on attempt 2 for:

- Linux / Python 3.11
- Linux / Python 3.13
- Windows / Python 3.11

All jobs completed as failures before any workflow step was exposed/executed.

## Minimal isolated probe

A dedicated diagnostic branch was created from the current C3 checkpoint:

- branch: `centinela-diagnostics/actions-prestep-probe-20260830`
- probe commit: `4fb3de881da9b8d4692387f34b4f8268a8e63aa4`
- workflow: `Centinela Actions Pre-step Probe`
- run id: `33325885812`

The probe deliberately contains no checkout, Python, uv, dependencies, project imports, secrets or application code. Its only job requests `ubuntu-latest` and its only intended step is a shell `echo` plus `uname -a`.

Result:

- workflow status: completed;
- conclusion: failure;
- elapsed execution control path: only a few seconds;
- job `Probe / Ubuntu`: failure;
- `steps=null`;
- `logs_url=null` in the normalized job evidence;
- the intended `echo` never ran.

## Conclusion

This proves the current failure is **not caused by**:

- F58 application code;
- MoneyPrinterTurbo imports;
- Python version selection;
- `uv sync`;
- Python dependencies;
- Ruff/pytest;
- Windows path setup;
- FFmpeg;
- Centinela scientific/media logic.

The verified classification is:

`CI_PRE_STEP_EXECUTION_BLOCKER / CONTROL_PLANE`

The remaining root-cause set is outside product code and includes repository/account Actions eligibility or controls such as runner allocation, quota/billing, Actions policy/permissions, or an equivalent GitHub control-plane condition.

The public GitHub Status page did not show a current global Actions incident when checked after the failure, so a global hosted-runner outage is **not verified** as the cause.

## Operational decision

- `PATCH_PRODUCT_CODE=FALSE`
- `BLIND_RERUN_LOOP=FALSE`
- `F58_APPLICATION_REGRESSION=NOT_DEMONSTRATED`
- `ACTIONS_ACCOUNT_OR_REPO_CONTROL_CHECK=PENDING`
- `F58_JUNIT=PENDING_STEP_EXECUTION`
- `SBOM_EXECUTION=PENDING_STEP_EXECUTION`

Do not spend cloud engineering time changing product code until a minimal probe can enter step execution.

## Recovery test

Once the account/repository Actions condition is believed resolved, re-run the minimal probe **once**. Only if `CENTINELA_ACTIONS_STEP_EXECUTION=PASS` appears should F58 and the C3 SBOM workflow be executed again.
