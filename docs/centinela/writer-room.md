# R6 Writer Room v0.1

R6 connects `RESEARCH` and `SCRIPT` to the R5 product coordinator.

## Fact Lock

Two safe modes exist:

- `GENERIC_GEOCENTRIC`: automatic for non-observation-specific subjects.
  Astronomy Core is evaluated at runtime, but the Fact Lock removes all
  observer-dependent facts such as altitude, azimuth, rise/set, culmination,
  twilight and local events. No user location is assumed.
- `OBSERVATION_CONTEXT`: used when the project supplies an explicit observer
  and optional timezone-aware moment.

Time-sensitive subjects such as "esta noche", visibility, conjunctions,
eclipses or "desde ..." require explicit observation context. Missing context
returns `NEEDS_INPUT`; it is never silently replaced with Valladolid or another
location.

## Writer Room

Twelve logical editorial stages are batched into three structured local Ollama
passes:

1. Creative Thesis + Story Architect + Hook Room + Draft.
2. Science Critic + Retention Critic + Visual Critic + Adversarial Reader.
3. Rewrite + Final Polish + Social Compression + pronunciation map.

The runtime reuses the existing loopback-only `OllamaLocalAdapter`.
No model is downloaded and MoneyPrinterTurbo's global cloud LLM provider is not
used by Writer Room.

Outputs:

- `fact_lock`
- `final_script`
- `writer_room_report`

Every scientific claim in the structured script must reference existing
`fact_id` values. `HECHO_VERIFICADO` claims can only reference
`HECHO_VERIFICADO` facts.

`final_script` always requires human review and is never approved for
publication automatically.
