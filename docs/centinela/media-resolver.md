# Centinela Media Resolver — R4

R4 connects the existing AstroMedia catalog, MaterialSelector, optional SemanticMatcher evidence and post-selection SmartFocal analysis to the R3 `MEDIA` stage. It does not replace those engines and does not fetch or generate media by itself.

## Authority and flow

`AstronomyVideoPlan` is the scene contract. Each scene already carries narration, visual requirement, astronomy objects, material keywords, AI-recreation permission and scientific status.

The flow is:

1. Read the `scene_plan` artifact from the previous SCENES receipt or an explicit artifact ID.
2. Optionally refresh AstroMedia only when `refresh_catalog=true`.
3. Query the existing AstroMedia catalog for bounded scene evidence.
4. Optionally run SemanticMatcher as secondary evidence only. R4 never changes MaterialSelector thresholds, provider priority, rights policy or real-before-AI policy based on semantic order.
5. Run the existing `MaterialSelector` as the final selection authority.
6. Run SmartFocal only on selected video material. Images and unresolved scenes are not analyzed.
7. Emit:
   - `material_selection`: the unchanged strict `MaterialSelectionPlan` contract used by downstream video planning.
   - `media_resolution`: R4 evidence containing normalized candidates, provider/rights data, semantic evidence and focal decisions.
8. If any scene remains `NO_ADEQUATE_MEDIA` or `AI_RECREATION_REQUIRED`, return `NEEDS_INPUT`; the Production Spine does not advance to `MEDIA_READY`.

R4 never substitutes an unresolved scene with unrelated B-roll.

## Catalog and providers

AstroMedia remains the catalog authority. Its existing provider enum already normalizes owned/local material plus NASA, ESA, Wikimedia, Pexels, Pixabay, Coverr, AI-generated material and other imported providers.

R4 V0.1 does not implement a new network downloader. Provider assets must already be materialized and indexed by AstroMedia/MPT before they can become selectable. This preserves a local-path contract for Video Base, provenance and reproducibility.

`refresh_catalog` defaults to false so a MEDIA job does not unexpectedly rescan `D:\ASTRONOMÍA\Medios`. When explicitly enabled it uses AstroMedia `DUPLICATE_CANDIDATES` hashing and may import existing MPT task artifacts; it does not use the network.

## Rights policy

The existing MaterialSelector remains authoritative:

- `RESTRICTED` is excluded.
- `CONFIRMED_OWNED` and `VERIFIED_LICENSE` are publication eligible.
- `UNVERIFIED` may be selected in draft production, but requires review and cannot make the material plan publication-ready.
- AI material is last resort only when both the request and the scene permit AI recreation.
- R4 does not generate AI media and does not invoke WanGP.

## SemanticMatcher

Semantic evidence defaults to disabled at the R4 request level. Enabling it still does not activate or download a model; the existing SemanticMatcher service keeps its own configuration gate and offline sidecar checks.

When available, semantic ordering is recorded as evidence/rank only. It cannot override MaterialSelector provider, rights, relevance or real-before-AI decisions. Failure or missing runtime is non-fatal and preserves deterministic material selection.

## SmartFocal

SmartFocal runs after selection and only for selected video. The existing safe wrapper is used with a fixed 1080x1920 target. Analysis failures fall back to centered COVER and are recorded in the R4 report. SmartFocal is not a material-selection authority.

## R3 integration

`build_media_stage_binding()` returns a `StageBinding` with:

- stage resource class: `MEDIUM`;
- network: false;
- LLM: false;
- render: false;
- automatic publication: false.

A complete resolution produces the required `material_selection` artifact and advances `SCENES_READY -> MEDIA_READY` through the existing Production Spine. An unresolved resolution persists both evidence artifacts but transitions the project to `NEEDS_INPUT`.

Cancellation is cooperative and `JobCancelled` is propagated back to the R2 JobManager rather than converted to a blocked project.

## Deferred

R4 does not implement the R5 product WebUI, R6 Writer Room, R7 audio/subtitle/delivery executors, R8 Review Studio/publication package, R9 Golden Real E2E, WanGP, model downloads, automatic publication or architecture freeze.
