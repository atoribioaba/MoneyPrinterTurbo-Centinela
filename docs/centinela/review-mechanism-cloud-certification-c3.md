# C3 Review Mechanism — Cloud Certification

Status: `PASS`
Date: `2026-08-31`
Working branch: `centinela-cert/c3-f58-readiness-v0.1`

## Scope

This certificate covers the cloud-executable Review/Finalization mechanism that is authoritative in the current pipeline:

`HumanFinalReviewRecord -> FinalizationE2E -> PublicationPackage -> F58`

It does **not** certify a real human review of a real Golden render. Real workstation media/hardware review remains local and pending.

## Canonical review contract

A human `APPROVE` decision is insufficient by itself. `FINALIZATION_E2E_PASS` requires all seven explicit review dimensions to pass:

1. `review_science`
2. `review_visual`
3. `review_audio`
4. `review_subtitles`
5. `review_rights`
6. `review_thumbnail`
7. `review_copy`

Together with `human_review_approved`, these form the eight canonical human-review checks required by a PASS plan.

Each individual review dimension is exercised adversarially as `false`; every case fails closed as `FINALIZATION_E2E_FAIL`.

Human review decisions are explicit:

- `APPROVE`: may continue only if all 7 review gates and all canonical final-render checks pass.
- `CHANGES_REQUESTED`: returns `HUMAN_REVIEW_CHANGES_REQUESTED` and blocks finalization/publication.
- `REJECT`: returns `HUMAN_REVIEW_REJECTED` and blocks finalization/publication.

`CHANGES_REQUESTED` and `REJECT` both preserve all publication side-effect guardrails.

## Safety invariants

The certified mechanism preserves all of the following:

- `REVIEW_APPROVED != AUTHORIZED_TO_PUBLISH`
- `human_review_required = true`
- `authorization_to_publish = false`
- `auto_publication = false`
- `uploads_files = false`
- `network_calls = 0`
- `webhook_calls = 0`
- `marks_published = false`
- `local_final_certification_required = true`

A forged `FINALIZATION_E2E_PASS` without recorded human review, without all canonical review checks, without both canonical final renders, or without their required evidence is rejected by validation before packaging.

Publication Package revalidates the `FinalizationE2EPlan` at its trust boundary instead of trusting a textual PASS status.

## Executable evidence — final strengthened Review run

- Workflow: `Centinela C3 Review Mechanism`
- Run: `33381224374`
- Head SHA: `ac933e44dd4f1cbcbb7a24b98213770fd707d243`
- Conclusion: `success`

Platform matrix:

| Platform | Python | Compile | Ruff | Contract tests | Cloud dry-run | Result |
|---|---:|---|---|---|---|---|
| Linux | 3.11 | PASS | PASS | PASS | PASS | PASS |
| Linux | 3.13 | PASS | N/A by workflow | PASS | PASS | PASS |
| Windows | 3.11 | PASS | N/A by workflow | PASS | PASS | PASS |

Linux 3.11 JUnit evidence:

- artifact id: `9753819837`
- artifact digest: `sha256:3b4a83a8a5d5d809cb807c1ff15316ab4aa2a47cc3f4990070a86483c2ee03c5`
- tests: `33`
- failures: `0`
- errors: `0`
- skipped: `0`

The 33-test suite includes explicit coverage for:

- `REJECT -> HUMAN_REVIEW_REJECTED`;
- `CHANGES_REQUESTED -> HUMAN_REVIEW_CHANGES_REQUESTED`;
- all seven review dimensions independently failing closed;
- legacy approval without explicit gate evidence;
- missing final-render SHA;
- forged PASS without canonical checks;
- forged PASS without final renders;
- approved review not authorizing publication;
- downstream Publication Package contract/API coverage.

Other Review JUnit artifacts:

- Linux 3.13 artifact id: `9753823872`
- Linux 3.13 digest: `sha256:3ff4822f2452b92c27083cbcf79df52eff2e65c1ec14454869ff5d9e43eaf140`
- Windows 3.11 artifact id: `9753827332`
- Windows 3.11 digest: `sha256:bc0b39981b6eb82b634ce888185ef450d5f3742268bc13790b6f4a23794954f9`

## Downstream Publication Package regression and fix

The strengthened Finalization contract exposed a stale Publication Package cloud dry-run. The contract tests themselves passed on all three platforms, but run `33381194085` failed only in `Run cloud-only publication package dry run` because that fixture manually fabricated a `FinalizationE2EPlan` using an obsolete aggregate `final_renders_verified` check.

This was a fixture drift defect, not a Publication Package service regression.

The fixture was corrected to obtain Finalization evidence through the authoritative `build_finalization_e2e()` service rather than duplicating the Finalization contract.

Final Publication Package downstream regression run:

- Workflow: `Centinela C3 Publication Package v0.2`
- Run: `33381572955`
- Head SHA: `ce35d1217cd409ab81e854f550d1f39f661398b5`
- Linux 3.11: PASS, including Ruff + contract + dry-run
- Linux 3.13: PASS, including contract + dry-run
- Windows 3.11: PASS, including contract + dry-run
- Overall: `success`

This makes the cloud dry-run consume the same Finalization authority as production code and prevents silent future drift between Review/Finalization and Publication Package fixtures.

## Downstream F58 regression evidence

F58 previously did not trigger when `finalization_e2e` model/service/tests changed. That was a CI regression-coverage gap because F58's manual Publication Package gate ultimately depends on the Finalization/Review trust chain.

The F58 workflow trigger surface was therefore bound to:

- `app/models/finalization_e2e.py`
- `app/services/finalization_e2e.py`
- `test/services/test_finalization_e2e.py`

Fresh F58 regression run:

- Workflow: `Centinela C3 F58 Readiness Mechanism`
- Run: `33381699046`
- Head SHA: `12671d1e8463a53e4b2efb2979c9fdc4f22b53a9`
- Linux 3.11: PASS, including Ruff + contract + semantic freeze guard
- Linux 3.13: PASS, including contract + semantic freeze guard
- Windows 3.11: PASS, including contract
- Overall: `success`

No freeze, activation, publication, runtime-config write, or human-approval semantics were weakened.

## Certified cloud state

```text
REVIEW_MECHANISM=PASS
REVIEW_MATRIX=3/3_PASS
REVIEW_CONTRACT_TESTS_LINUX311=33_PASS
SCIENCE_GATE=FAIL_CLOSED
VISUAL_GATE=FAIL_CLOSED
AUDIO_GATE=FAIL_CLOSED
SUBTITLES_GATE=FAIL_CLOSED
RIGHTS_GATE=FAIL_CLOSED
THUMBNAIL_GATE=FAIL_CLOSED
COPY_GATE=FAIL_CLOSED
REJECT_BLOCKS=TRUE
CHANGES_REQUESTED_BLOCKS=TRUE
REVIEW_APPROVED!=AUTHORIZED_TO_PUBLISH
AUTO_PUBLICATION=FALSE
UPLOADS_FILES=FALSE
NETWORK_CALLS=0
WEBHOOK_CALLS=0
MARKS_PUBLISHED=FALSE
HUMAN_REVIEW_REQUIRED=TRUE
LOCAL_FINAL_CERTIFICATION_REQUIRED=TRUE
PUBLICATION_PACKAGE_DOWNSTREAM=3/3_PASS
F58_DOWNSTREAM=3/3_PASS
REAL_HUMAN_REVIEW=PENDING_LOCAL
```

## Boundary

This certificate validates mechanism semantics and fail-closed behavior using synthetic cloud fixtures. It does not claim:

- real Golden E2E approval;
- real media quality approval;
- real audio/subtitle subjective acceptance;
- real rights/manual checklist sign-off;
- authorization to publish;
- local workstation certification;
- architecture freeze authorization.

Those remain separate local/human gates.
