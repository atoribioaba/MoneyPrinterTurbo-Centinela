# Centinela V1 — Backup & Recovery Drill Contract

Status: pre-V1 specification. No destructive restore is authorized.

## Goal

A backup is only considered valid when a restore can be demonstrated into a **new, non-destructive location** and the restored environment can reproduce the critical project state without exposing secrets.

## Required backup set

### Git / code
- canonical V1 RC branch + exact commit SHA;
- all tags required for recovery;
- `pyproject.toml`, `uv.lock`, workflows and scripts;
- final SBOM and dependency inventory;
- final configuration templates;
- release notes and certification evidence.

### Preserved local state before reconciliation
- original local branch/HEAD;
- `git status --porcelain=v1 --branch` evidence;
- stash list + preservation stash SHA/message;
- hashes/copies of known untracked files;
- dedicated backup branch for the exact committed local lineage.

Do not use stash as the only copy of irreplaceable work.

### Runtime inventory
- Windows build;
- Python and uv versions;
- NVIDIA driver / reported CUDA capability;
- exact FFmpeg/FFprobe build/configuration;
- Ollama/llama.cpp/runtime versions when selected;
- selected LLM/TTS/visual model IDs, versions and hashes where feasible;
- no API keys or bearer tokens in evidence artifacts.

### Media / AstroMedia
- AstroMedia database/catalog backup;
- sidecars and rights/provenance metadata;
- deterministic hashes for catalog-critical media;
- separate backup strategy for large original media under `D:\ASTRONOMÍA\Medios`;
- never assume a Git backup contains the media library.

### Generated evidence
- Golden project manifest;
- FactLock records;
- selected media provenance;
- VIDEO_BASE/master/social manifests;
- Review 7/7 evidence;
- Publication Package evidence;
- final F58 readiness report.

## Secret policy

Secrets are backed up only through an appropriate private secret-management method outside Git evidence. Recovery documentation records **names/requirements**, never secret values.

## Non-destructive recovery drill

1. Create a fresh recovery directory on a different path from the working repository.
2. Restore/clone the exact V1 RC commit.
3. Recreate the Python environment from the lockfile.
4. Re-run secret-safe runtime inventory.
5. Verify imports and targeted smoke tests.
6. Run the full test suite where practical.
7. Restore AstroMedia metadata/catalog into an isolated location.
8. Validate that referenced owned-media entries resolve to the intended files/hashes without rewriting originals.
9. Validate FactLock/ArtifactStore/ProjectManifest readability.
10. Validate startup and clean shutdown.
11. Validate FFmpeg probe and one non-destructive encode fixture.
12. Do **not** publish anything during recovery validation.

## Pass criteria

`RECOVERY_DRILL=PASS` requires:
- exact RC SHA restored;
- clean dependency reconstruction or a documented reproducible exception;
- no secret leakage;
- critical manifests readable;
- AstroMedia metadata recoverable;
- selected rights/provenance preserved;
- targeted/full tests meet the V1 release threshold;
- startup/shutdown works;
- generated outputs remain blocked from automatic publication;
- recovery happens without overwriting the original working copy.

## Fail-closed conditions

Fail the drill if:
- the only copy of work exists in a stash/untracked file;
- media rights/provenance cannot be restored;
- selected model/runtime version is unknown and affects reproducibility;
- secrets appear in logs/manifests;
- restore requires undocumented manual mutation;
- publication can occur automatically after restore.

## Evidence output

Record:
`SOURCE_RC_SHA | RESTORE_PATH | LOCK_HASH | SBOM_HASH | ASTROMEDIA_DB_HASH | MANIFEST_HASHES | TEST_RESULT | START_STOP_RESULT | FFMPEG_RESULT | SECRET_SCAN | AUTO_PUBLICATION | DRILL_RESULT`

Permanent invariant: `AUTO_PUBLICATION=FALSE`.
