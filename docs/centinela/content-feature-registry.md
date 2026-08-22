# F36 · Content Feature Registry

Version: `content-feature-registry-v0.1`.

F36 turns the approved planning state into a deterministic numeric feature
snapshot suitable for later analytics joins.

The registry deliberately stores numeric structural descriptors, not the full
creative text. Current features include duration, scene count, hook/narration
lengths, claim count, AI-recreation scene count, distinct astronomy-object
count, placeholder count, narrative intensity and climax position.

A snapshot can be bound explicitly to `(platform, content_id)`. Without that
binding the real run remains `WAITING_FOR_CONTENT_BINDING`.

No pixels are analyzed, no LLM is called, no database is written and no
publication action exists.
