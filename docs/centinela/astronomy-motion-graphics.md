# F16 · Astronomy Motion Graphics

Version: `astronomy-motion-graphics-v0.1`

F16 plans cinematic overlays from **explicit F3 plan data only**.

It may use:

- `ScenePlan.astronomy_objects`;
- `ScenePlan.claims`;
- the exact scientific status;
- `fact_ids` already attached to claims.

It does not compute astronomy and does not infer where an object is on screen.

## Allowed cues

- `OBJECT_LABEL`
- `SCIENTIFIC_CLAIM_CALLOUT`

## Forbidden invention

F16 does not invent:

- screen coordinates of the Moon/Sun/planet;
- orbital trajectories;
- apparent motion vectors;
- distances;
- percentages;
- dates;
- angles;
- magnitudes.

Any future object-following overlay must consume verified F11 tracking rather
than guessing a position.

## Scientific labels

`HECHO_VERIFICADO` claim callouts preserve their `fact_ids`.

Other statuses remain visible as their actual status and can require review.

## Rendering

F16 is planning-only.

It does not render graphics, download assets, call an LLM, use the GPU or
publish.

`plan_claims_only = true`: F16 never creates a new scientific claim. For claims already marked `HECHO_VERIFICADO`, existing `fact_ids` are preserved exactly.
