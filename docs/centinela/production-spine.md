# Centinela Real Production Spine — R3

R3 adds the executable application layer between the R1 project/artifact foundation, the R2 state/job runtime and the existing F3–F58 domain services. It does not replace F51 `production_orchestrator.py`; F51 remains a deterministic late-stage planner with its original guardrails.

## Stage contract

The spine advances only one canonical R2 state at a time: RESEARCH, SCRIPT, SCENES, MEDIA, AUDIO, VIDEO_BASE, REVIEW_PREP and PUBLICATION_PACKAGE. Human approval is deliberately outside the job adapters and is recorded only through `record_human_review()`.

Every successful stage must materialize its required immutable artifact type plus a `spine_stage_receipt`. The receipt carries the input fingerprint, adapter identity, output IDs and SHA-256 values. State advances only after output artifacts and the receipt are safely registered in R1.

If a retry sees the same durable receipt while the project is still in the source state, it reuses the receipt and advances state without rerunning the adapter. Partially written artifacts are never deleted automatically.

## Capability gaps

R3 does not fabricate missing R4/R6/R7/R8 capabilities. If a required adapter is not registered, the project moves to `NEEDS_INPUT` with the roadmap owner recorded. Registering the adapter and explicitly scheduling the same stage resumes the project to its prior state and continues.

## Resources

R3 reuses the existing `ResourceGovernor` by default. Binding a stage below its minimum resource class is rejected. Network adapters and EXCLUSIVE adapters require explicit opt-in. WanGP is not registered or invoked by R3.

## Safety

Automatic publication is rejected at adapter-registration time. `PUBLICATION_PACKAGE_READY` means the package is ready for the manual publication policy; it never means content was posted. R3 adds a namespaced SQLite metadata table and a non-destructive partial unique index that prevents two active jobs for the same project/stage across processes.

Legacy F3–F58 files can be explicitly ingested through `LegacyArtifactIngestAdapter`; source files are copied through R1 and are never moved or deleted.

## Deferred

R4 supplies the unified Media Resolver. R5 supplies the product WebUI. R6 supplies Writer Room. R7 supplies production audio/subtitle/delivery executors. R8 supplies Review Studio and the materialized Publication Package. R9 remains the real Golden E2E certification.
