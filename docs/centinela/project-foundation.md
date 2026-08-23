# Centinela Project Foundation — R1

R1 introduces the persistent project/artifact foundation used by later Centinela orchestration layers. It does not replace the existing F3–F58 engineering services and does not define R2 workflow transitions.

## Canonical storage

Runtime data lives under `storage/centinela/`, which is already ignored by Git.

- `centinela.db`: rebuildable SQLite index.
- `projects/<project_id>/manifest.json`: canonical project manifest.
- `projects/<project_id>/artifacts/`: immutable generated or ingested artifact bytes.

The filesystem manifest and artifact bytes are canonical. SQLite is a derived index and can be rebuilt with `ArtifactStore.reindex_project()`.

## Contracts

`ArtifactRef` stores artifact identity, type, schema version, relative path, SHA-256, size, producer, producer version, input artifact IDs, provenance and metadata.

`ProjectManifest` stores project identity, status, timestamps, observation context, metadata, all artifact references, latest artifact by type, and the active runtime snapshot artifact.

`RuntimeSnapshot` stores effective Git/application/Python/platform information, FFmpeg/encoder data and caller-supplied LLM/TTS/media/render/runtime settings. Secret-like keys are rejected; the snapshot does not read `config.toml`.

## Integrity and safety

Project/artifact identifiers are path-safe. Artifact paths are constrained below the Centinela storage root. Existing symlink components are rejected. Writes use same-directory temporary files, `fsync`, and `os.replace`. Artifact bytes are SHA-256 verified on read.

Declared artifact inputs must already exist in the same project, so dependency edges always point to previously registered artifacts. SQLite indexes both artifacts and dependency edges.

`audit_project()` verifies artifact bytes, manifest/index agreement, dependency edges and SQLite integrity. SQLite connection contexts explicitly close their OS handles so Windows can delete or replace project stores immediately after an operation. Schema version 1 is installed only into an empty/unversioned database; an unversioned database that already contains tables is refused rather than destructively rebuilt. Databases newer than the supported schema are refused rather than downgraded.

## Legacy compatibility

`ingest_file()` copies an existing phase artifact into the project store, leaves the source untouched and records the canonical original absolute path plus source SHA-256 in provenance. Those reserved provenance fields, the source filename metadata, and JSON media type cannot be overridden by caller metadata. Existing F3–F58 evidence is not moved or deleted.

## Deferred to later roadmap stages

R1 intentionally does not implement the R2 state machine/job manager, Production Spine, Writer Room, Media Resolver, final WebUI, WanGP, model downloads, automatic publication or architecture freeze.
