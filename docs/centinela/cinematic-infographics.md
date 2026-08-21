# F17 · Cinematic Infographics

Version: `cinematic-infographics-v0.1`

F17 converts **existing F3 scientific claims** into cinematic infographic card
specifications.

It does not research or add facts.

## HECHO_VERIFICADO

A verified card is `grounding_ready=true` only when the F3 claim already
carries `fact_ids`.

This reuses the F3 invariant that `HECHO_VERIFICADO` claims must be grounded.

F17 **never** marks a card as publication-ready. Every card keeps
`human_review_required=true`, preserving:

`GENERAR → REVISAR → APROBAR → PUBLICAR`

## Other statuses

- `APROXIMACION_DIVULGATIVA`
- `HIPOTESIS`
- `RECREACION_VISUAL`
- `INFERENCIA`
- `NO_VERIFICADO`

are preserved exactly. All cards require human review in F17 V0.1.

## No invented charts

F17 does not infer numeric series from prose.

It does not produce:

- fake scales;
- fake percentages;
- fake distances;
- fake timelines;
- fake orbital plots;
- charts with invented values.

A later charting phase would need structured verified data, not prose parsing.

## Rendering

Planning-only. No GPU, LLM, external assets, web search or publication.
