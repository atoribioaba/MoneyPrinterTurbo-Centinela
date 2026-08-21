# F29 · Automated Quality Gates

Version: `quality-gates-v0.1`.

F29 aggregates deterministic readiness signals from visual quality, enhancement
review, sound-design assets, voice selection, mastering and subtitle timing.

It can produce only two states:

- `BLOCKED`;
- `READY_FOR_HUMAN_REVIEW`.

It never publishes. Even with every technical check passing, the project policy
remains:

`GENERAR → REVISAR → APROBAR → PUBLICAR`.

Human approval is therefore mandatory and encoded in the model contract.
