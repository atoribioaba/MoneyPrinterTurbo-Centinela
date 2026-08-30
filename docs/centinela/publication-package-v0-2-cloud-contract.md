# Publication Package v0.2 — cloud contract proposal

Date: 2026-08-30
Status: design/contract ready; production-code change should execute only with targeted tests available.

## Why this is needed

The current `publication-package-v0.1` service explicitly plans these assets when finalization and metadata are ready:

1. `master_2160x3840.mp4`
2. `social_1080x1920.mp4`
3. `caption.txt`
4. `metadata.json`
5. `publication-checklist.json`

The canonical Centinela package additionally requires explicit deliverables for:

- `thumbnail.jpg`
- `subtitles-es.srt`
- YouTube title/description copy
- hashtags/caption copy
- sources/licenses/provenance
- review metadata/checklist

Therefore `READY_FOR_MANUAL_PACKAGE` is currently weaker than the canonical package definition.

## Non-negotiable safety contract

v0.2 must remain planning-only:

- `manual_publication_only=true`
- `writes_files=false`
- `uploads_files=false`
- `network_calls=0`
- `auto_publication=false`
- `APPROVED != AUTHORIZED_TO_PUBLISH`

No cloud dry-run may create a real publication or claim human approval.

## Proposed backward-compatible input extension

Add an optional publication-support manifest rather than overloading `FinalizationE2EPlan` with non-video assets.

Proposed conceptual fields:

- thumbnail probe/path + presence + optional SHA256;
- subtitle probe/path + presence + optional SHA256;
- sources/licenses/provenance manifest probe/path + presence + optional SHA256;
- review checklist probe/path + presence + optional SHA256;
- metadata remains structured (`title`, `caption`, `hashtags`, `youtube_description`).

All new request fields should have safe defaults so historical callers can still construct the request; however historical requests that lack canonical required assets must not be promoted to the stronger v0.2 ready status.

## Proposed required asset list

| Asset id | Target filename | Required for canonical ready |
|---|---|---:|
| master | `master_2160x3840.mp4` | yes |
| social | `social_1080x1920.mp4` | yes |
| thumbnail | `thumbnail.jpg` | yes |
| subtitles_es | `subtitles-es.srt` | yes |
| caption | `caption.txt` | yes |
| metadata | `metadata.json` | yes |
| provenance | `sources-licenses-provenance.json` | yes |
| publication_checklist | `publication-checklist.json` | yes |

YouTube title/description and hashtags can remain structured inside `metadata.json` if that schema is explicit and tested; a separate text file is optional rather than required.

## Proposed statuses

Retain historical statuses and add a fail-closed asset gate:

- `WAITING_FOR_FINALIZATION`
- `WAITING_FOR_METADATA`
- `WAITING_FOR_REQUIRED_ASSETS`
- `READY_FOR_MANUAL_PACKAGE`

`READY_FOR_MANUAL_PACKAGE` requires:

1. finalization is `FINALIZATION_E2E_PASS`;
2. metadata is present and valid;
3. all canonical required asset probes are present;
4. rights/provenance manifest is present;
5. safety flags remain planning-only/manual-only.

## Tests to add before implementation is considered certified

1. waits for finalization;
2. waits for metadata after finalization pass;
3. waits for required assets if thumbnail missing;
4. waits for required assets if subtitles missing;
5. waits for required assets if provenance missing;
6. ready only when every required asset is present;
7. deterministic package hash for identical stable inputs;
8. extra fields fail closed through strict Pydantic models;
9. `auto_publication` cannot become true;
10. writes/uploads/network remain zero/false;
11. F58 remains blocked if Publication Package is not canonical-ready.

## Cloud dry-run fixture

Use synthetic paths and hashes only. Do not access `D:`/`E:` or local media. The fixture should represent:

- two video probes from a synthetic `FINALIZATION_E2E_PASS`;
- synthetic thumbnail and subtitles probes;
- synthetic provenance manifest;
- deterministic metadata.

Expected output:

`PUBLICATION_PACKAGE_CLOUD_DRY_RUN=PASS`
`REAL_MEDIA_USED=FALSE`
`WRITES_FILES=FALSE`
`UPLOADS_FILES=FALSE`
`NETWORK_CALLS=0`
`AUTO_PUBLICATION=FALSE`
`LOCAL_FINAL_CERTIFICATION_REQUIRED=TRUE`

## Implementation decision

Do not modify v0.1 production behavior blindly while GitHub Actions cannot execute steps. Preferred sequence:

1. preserve this contract;
2. prepare code/tests on an isolated branch;
3. execute targeted Linux 3.11/3.13 + Windows 3.11 tests when runners recover;
4. only then consider selective reconciliation into the V1 candidate after the PC returns.

This gap is cloud-doable and should not consume the first PC session unless runner unavailability persists through 2026-09-08.
