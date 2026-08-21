# F31 · Analytics Brain

Version: `analytics-brain-v0.1`.

This phase defines the canonical analytics observation contract. It deliberately
does not call YouTube, Instagram or TikTok APIs and does not persist account
data yet.

Every observation retains:

- platform;
- content identifier;
- native metric name;
- native unit/value type;
- observation timestamp;
- source type and optional source reference;
- semantic-confidence label;
- optional normalized timeline position for retention observations.

Storage decision:

- initial candidate: SQLite, core in the public domain, no extra service;
- future OLAP candidate: DuckDB, MIT;
- V0.1 writes neither database.

The objective is provenance before optimisation: an unknown metric remains
native instead of being silently translated into a supposedly equivalent
cross-platform metric.
