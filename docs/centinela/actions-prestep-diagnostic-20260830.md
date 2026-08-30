# GitHub Actions pre-step diagnostic — 2026-08-30

Status: `CONTROL_PLANE_BLOCKER_CONFIRMED`

This diagnostic separates MoneyPrinterTurbo/Centinela product failures from GitHub Actions runner-allocation/control-plane failures. It does **not** assert a billing/quota root cause without billing-page evidence.

## 1. Dedicated F58 evidence

Dedicated F58 run: `33323286894`, attempt 2.

Jobs:

- Linux / Python 3.11
- Linux / Python 3.13
- Windows / Python 3.11

Raw GitHub Actions job metadata for all three jobs shows:

- `status=completed`
- `conclusion=failure`
- `steps=[]`
- `runner_id=0`
- `runner_name=""`
- `runner_group_id=0`
- `runner_group_name=""`

The Linux jobs requested `ubuntu-latest`; the Windows job requested `windows-latest`.

All three jobs were created/started at `2026-08-30T17:31:29Z` and completed at `2026-08-30T17:31:31Z` without runner assignment or step execution.

Therefore:

`F58_RUNNER_ASSIGNED=FALSE`

`F58_PRODUCT_CODE_EXECUTED=FALSE`

## 2. Minimal isolated probe

Diagnostic branch:

- branch: `centinela-diagnostics/actions-prestep-probe-20260830`
- commit: `4fb3de881da9b8d4692387f34b4f8268a8e63aa4`
- workflow: `Centinela Actions Pre-step Probe`
- run id: `33325885812`

The workflow contains only:

- `runs-on: ubuntu-latest`
- `permissions: contents: read`
- one shell step that should print `CENTINELA_ACTIONS_STEP_EXECUTION=PASS` and run `uname -a`

It contains no checkout action, Python setup, uv, dependencies, project imports, secrets, FFmpeg, MoneyPrinterTurbo/Centinela code or external service call.

Raw job metadata:

- job: `Probe / Ubuntu`
- `status=completed`
- `conclusion=failure`
- `steps=[]`
- `runner_id=0`
- `runner_name=""`
- `runner_group_id=0`
- `runner_group_name=""`
- requested label: `ubuntu-latest`
- created/started: `2026-08-30T17:39:54Z`
- completed: `2026-08-30T17:39:55Z`

The intended shell step never ran.

Therefore:

`MINIMAL_PROBE_RUNNER_ASSIGNED=FALSE`

`CENTINELA_ACTIONS_STEP_EXECUTION=NOT_REACHED`

## 3. Repository/account-side evidence available through the connector

Repository: `atoribioaba/MoneyPrinterTurbo-Centinela`.

Verified repository state:

- visibility: private
- archived: false
- authenticated owner permission: `admin`
- repository permissions exposed by GitHub: `admin=true`, `maintain=true`, `push=true`, `pull=true`, `triage=true`

This rules out lack of owner/repository write/admin permission as the demonstrated cause.

The repository rulesets endpoint returns HTTP `403` with GitHub's explicit message:

`Upgrade to GitHub Pro or make this repository public to enable this feature.`

GitHub's current official documentation states that rulesets on **private** repositories require GitHub Pro, Team or Enterprise Cloud; GitHub Free supports rulesets only on public repositories. This is strong plan-level evidence consistent with a GitHub Free personal-account repository, but this diagnostic does not substitute that inference for direct billing-plan/usage data.

The GitHub connector used for this audit does **not** expose the account Billing/Usage/Budgets pages or the repository Actions-permissions endpoint. Those fields therefore remain unverified here rather than inferred.

## 4. Timing boundary

Latest verified successful GitHub-hosted-runner evidence currently identified in this repository:

- workflow: `Centinela VISUAL_RECREATION Cloud Replay`
- run: `33320062923`
- exact F57 checkpoint: `a88f08fe9ae44cb24dafd8044a7b0b45e678d5d6`
- created: `2026-08-30T15:35:20Z`
- conclusion: `success`

Later control-plane evidence:

- F58 attempt 2 at `17:31:29Z`: no runner assigned on Ubuntu or Windows
- minimal probe at `17:39:54Z`: no runner assigned on Ubuntu

Thus GitHub-hosted runner execution was demonstrably available earlier on 2026-08-30 and unavailable for these later jobs. The exact transition cause is not exposed by the workflow/job APIs available here.

## 5. Official GitHub billing facts relevant to this symptom

Current GitHub documentation states:

- standard GitHub-hosted runners are metered for private repositories;
- GitHub Free includes 2,000 Actions minutes per month;
- included minutes reset at the start of the billing cycle;
- if an account has no valid payment method, Actions usage is blocked after the included quota is exhausted;
- if a blocking Actions budget reaches its limit, GitHub-hosted-runner usage can be blocked until the budget/cycle condition changes.

These facts make **quota / billing / budget eligibility** the leading hypothesis for the observed no-runner condition, especially because both `ubuntu-latest` and `windows-latest` fail before allocation.

However, the following are deliberately **not** asserted without direct billing-page evidence:

- `ACTIONS_INCLUDED_MINUTES_EXHAUSTED`
- `PAYMENT_METHOD_INVALID_OR_ABSENT`
- `ACTIONS_BUDGET_HARD_STOP_REACHED`
- exact remaining Actions minutes
- exact billing-cycle reset date

## 6. Cause classification

Proven:

`CI_PRE_STEP_EXECUTION_BLOCKER=TRUE`

`CONTROL_PLANE_BLOCKER_CONFIRMED=TRUE`

`RUNNER_ALLOCATION_OCCURRED=FALSE`

`F58_APPLICATION_REGRESSION=NOT_DEMONSTRATED`

`PRODUCT_PATCH_REQUIRED=FALSE`

`BLIND_RERUN_LOOP=FALSE`

Leading but not yet proven root-cause class:

`ACTIONS_QUOTA_BILLING_OR_BUDGET=PRIMARY_HYPOTHESIS`

Still possible because connector-visible evidence cannot inspect them directly:

- account/repository Actions policy or eligibility control;
- quota exhaustion;
- missing/invalid payment method after quota exhaustion;
- blocking Actions budget;
- equivalent GitHub account-level control.

A global hosted-runner outage is not asserted; the public GitHub Status page did not show a matching global Actions incident when previously checked.

## 7. Exact non-PC verification still required

This can be checked from the GitHub web/mobile account UI; no Windows workstation is required.

Verify the personal account billing/usage pages for:

1. GitHub plan shown for the personal account;
2. GitHub Actions included usage consumed / remaining;
3. whether the included quota has reached 100%;
4. valid payment-method status, if paid overage is intended;
5. `Budgets and alerts` entries affecting GitHub Actions;
6. whether any applicable budget has `Stop usage when budget limit is reached` enabled and exhausted;
7. any GitHub banner/message explicitly explaining Actions suspension or billing restriction.

Do not expose payment details, tokens or other sensitive values in project logs. Only record the minimum categorical evidence needed, for example:

- `GITHUB_PLAN=FREE|PRO|OTHER`
- `ACTIONS_INCLUDED_USAGE_EXHAUSTED=TRUE|FALSE`
- `ACTIONS_BUDGET_BLOCK=TRUE|FALSE`
- `PAYMENT_OVERAGE_ENABLED=TRUE|FALSE|NOT_APPLICABLE`

## 8. Recovery protocol

Do **not** patch F58, SBOM, Publication Package or preview product code to work around this condition.

Once the account/repository Actions restriction is actually resolved or the billing cycle restores eligibility:

1. re-run the minimal probe **once**;
2. require `CENTINELA_ACTIONS_STEP_EXECUTION=PASS`;
3. only then run F58 once;
4. only then execute the prepared C3 CycloneDX SBOM workflow;
5. classify any subsequent step-level failure independently as regression, hermeticity issue or historical debt.

Until then:

`F58_JUNIT=PENDING_STEP_EXECUTION`

`SBOM_EXECUTION=PENDING_STEP_EXECUTION`

`LOCAL_CERTIFICATION_REQUIRED=TRUE`

`MERGE_AUTHORIZED=FALSE`

`AUTO_PUBLICATION=FALSE`

`ARCHITECTURE_FREEZE_AUTHORIZED=FALSE`
