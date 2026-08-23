# R5 · Product WebUI Control Center v0.1

R5 turns the existing Streamlit installation into a product-facing shell for **EL CENTINELA DEL UNIVERSO** without deleting or rewriting the F3–F58 engineering pages.

## Product boundary

The normal workflow is organized as:

- PRODUCCIÓN: Inicio, Crear vídeo, Proyectos, Revisión.
- ASTRONOMÍA: Observatorio, Efemérides.
- MEDIOS: Biblioteca, Fuentes.
- RESULTADOS: Publicación, Analítica.
- SISTEMA: Estado, Configuración.
- AVANZADO · INGENIERÍA: legacy MoneyPrinterTurbo UI and F3–F58 diagnostic pages.

`webui/Centinela.py` is the new Streamlit entrypoint. `webui/Main.py` and `webui/pages/*.py` remain intact and are explicitly registered under the advanced engineering group.

## Application layer

`CentinelaControlCenter` is an in-process application service used by Streamlit and suitable for later API/CLI consumers. It composes:

- R1 `ArtifactStore`.
- R2 `ProjectStateMachine` and `JobManager`.
- R3 `ProductionSpine`.
- R4 `MediaResolver`.

The UI does not call localhost HTTP to reach these services.

## Automatic pipeline coordinator

Creating a project can enqueue one product-level job: `centinela.product.pipeline`.

The coordinator repeatedly inspects `ProductionSpine.project_status()` and automatically schedules the next stage only when a real adapter is registered. It never fabricates missing R6/R7/R8 outputs. A missing capability returns `CAPABILITY_PENDING` while preserving the current project state.

The coordinator and stage jobs share a two-worker `JobManager`; one worker can supervise while the second executes the current stage. No automatic retry is introduced.

## Automatic media handling

The normal product workflow has no manual Index/Search/SmartFocal step.

Before scheduling R4 MEDIA, `MediaAutomationPolicy` performs a cheap recursive stat preflight over `D:\ASTRONOMÍA\Medios` and compares current files against AstroMedia catalog metadata:

- new media;
- removed media;
- size/mtime changes;
- `.astromedia.json` sidecar changes.

Only when a difference exists does the coordinator send `refresh_catalog=true` to R4. R4 then performs its existing incremental `index_library()` path. This avoids forcing a full catalog refresh for every video.

SemanticMatcher remains disabled by default pending its A/B/resource benchmark. SmartFocal remains enabled post-selection through R4. No AI generation or WanGP is triggered by R5.

## Human boundaries

The system may stop for:

- missing future capability;
- `NEEDS_INPUT`;
- `BLOCKED`;
- explicit human review.

Human review is exposed as an explicit approval/rejection action. Publication is never automatic.

## Versioning

R5 displays separate product/core identities:

- Centinela Edition: `pre-V1`.
- MoneyPrinterTurbo Core: read from `pyproject.toml` (1.3.4 at the R5 baseline).

R5 does not authorize architecture freeze and does not declare Centinela V1.
