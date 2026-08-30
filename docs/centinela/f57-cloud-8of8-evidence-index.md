# F57 cloud 8/8 evidence index

Date: 2026-08-30
Exact checkpoint: `a88f08fe9ae44cb24dafd8044a7b0b45e678d5d6`
Recovery branch: `centinela-backup/cloud-f57-8of8-20260830`

## Authority boundary

`F57_CLOUD=8/8_PASS`

This means the cloud/hermetic scenario contracts are closed. It does **not** certify the unavailable local Windows workstation, RTX 2060, real local AstroMedia corpus, local Qwen3-TTS, actual NVENC runtime or final human review.

`CLOUD_PASS_IS_NOT_LOCAL_FINAL_AUTHORITY=TRUE`
`LOCAL_RTX_2060_CERTIFICATION_REQUIRED=TRUE`
`AUTO_PUBLICATION=FALSE`

## Scenario matrix

| # | Scenario | Cloud status | Required cloud gate semantics | Local authority still required |
|---:|---|---|---|---|
| 1 | SOL_TO_MOON | PASS | science, visual relevance, provenance, render, no irrelevant B-roll, recovery | real own-media/AstroMedia + hardware render |
| 2 | LUNAR | PASS | MEDIA 5/5 with specific/scientific visuals, fail-closed grounding | real local catalog/media + final content review |
| 3 | PLANETARY | PASS | same six F57 gates | real local catalog/media + hardware render |
| 4 | ECLIPSE | PASS | same six F57 gates; recreation semantics must remain explicit where used | local render + content/science review |
| 5 | CONSTELLATION | PASS | same six F57 gates | real local catalog/media + hardware render |
| 6 | DEEP_SKY | PASS | same six F57 gates | real local catalog/media + hardware render |
| 7 | INSUFFICIENT_MEDIA | PASS AS CONTROLLED FAILURE CONTRACT | must fail closed / NEEDS_INPUT instead of filling with irrelevant B-roll | repeat fail-closed behavior locally |
| 8 | VISUAL_RECREATION | PASS | explicit recreation label/provenance, not a real observation/event, publication not ready by default | local final review and policy confirmation |

## Mandatory gate fields per scenario

Every normal F57 scenario evidence must account for:

- `scientific_pass`
- `visual_relevance_pass`
- `provenance_pass`
- `render_pass`
- `no_irrelevant_broll`
- `recovery_pass`

Final performance evidence also requires:

- `oom_events=0`
- `unrecovered_failures=0`
- NVENC path tested locally
- libx264 fallback tested locally

Cloud CPU/libx264 success cannot substitute for NVENC certification.

## VISUAL_RECREATION specific contract

The preserved cloud workflow requires, among other properties:

- five selected recreation assets in the scenario fixture;
- all selected assets explicitly AI/recreation class;
- `represents_real_observation=false`;
- `represents_real_event=false`;
- `publication_ready=false`;
- recreation labeling present;
- provenance contract pass;
- visual relevance pass;
- no irrelevant B-roll;
- `auto_publication=false`;
- `network_discovery=false`;
- MaterialSelector remains final authority;
- human review and local final certification remain required.

## INSUFFICIENT_MEDIA specific contract

Success for this scenario is **not** fabricating a complete video. Success is demonstrating that insufficient relevant/verified material blocks progression predictably and does not trigger irrelevant B-roll or silent scientific relaxation.

Expected semantic result: `NEEDS_INPUT` / controlled fail-closed behavior.

## Lunar continuity note

Lunar cloud evolved from an earlier real Golden that physically reached review but was human-rejected for content quality. The later cloud 5/5 result closes the media-selection/scientific-visual contract only; it does not erase the need to re-review hook, visuals, brightness, thumbnail, voice and subtitles in the real local Golden.

## Local rerun order after reconciliation

1. targeted F57 runner/tests;
2. real AstroMedia availability;
3. Lunar real 5/5;
4. remaining normal scenarios;
5. INSUFFICIENT_MEDIA controlled fail;
6. VISUAL_RECREATION labeling/recovery;
7. NVENC + libx264 paths;
8. RAM/VRAM/OOM evidence;
9. full Golden E2E;
10. human review.

## Freeze implication

F57 cloud 8/8 removes a major cloud-development blocker, but F58 must remain `NOT_READY_FOR_ARCHITECTURE_FREEZE` until the real Golden, canonical manual Publication Package and complete verified OSS audit are available.
