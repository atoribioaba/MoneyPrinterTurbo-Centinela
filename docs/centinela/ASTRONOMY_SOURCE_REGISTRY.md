# Centinela astronomy source registry

Date: 2026-09-09

This registry separates deterministic calculation libraries, data providers, catalogs, forecasts and safety authorities. A source being open or authoritative does not make every derived statement a `HECHO_VERIFICADO`.

| Source | Role | Current licence/status | Centinela decision |
|---|---|---|---|
| Astronomy Engine (`cosinekitty/astronomy`) | deterministic solar-system and fixed-J2000 local geometry | MIT | `MANTENER` |
| NASA Science | eclipses / missions / solar safety / primary public science context | U.S. government/public-source terms vary by asset | `PRIMARY_AUTHORITY` |
| ESA | missions / discoveries / spacecraft science | official source; asset terms per item | `PRIMARY_AUTHORITY` |
| IGN España | official Spanish astronomical/geographic context where applicable | official source; terms per dataset/page | `PRIMARY_AUTHORITY_ES` |
| IAU | nomenclature / standards / astronomical authority | official body | `PRIMARY_AUTHORITY` |
| IAU Meteor Data Center (MDC) | official database/list of known meteor showers and nomenclature authority with the IAU WG Meteor Shower Nomenclature | authoritative IAU database; bulk redistribution/API licence and machine-readable ingestion contract not verified in this checkpoint | `PRIMARY_AUTHORITY`; `LICENCIA NO VERIFICADA` for automated bulk ingestion; do not scrape silently |
| NASA/JPL Horizons (`ssd.jpl.nasa.gov/api/horizons.api`) | observer-dependent ephemerides for comets, asteroids and other Horizons targets | official NASA/JPL data service; Horizons API documentation version 1.3 (2025 June); SSD API fair-use policy applies | `PRIMARY_AUTHORITY`; delegate small-body ephemerides here rather than unvalidated local orbit propagation |
| Open-Meteo | ordinary meteorological forecasts | API data CC BY 4.0; server AGPLv3 | `OSS CON SERVICIO DE PAGO`; free/open-data use with attribution where applicable |
| 7Timer! ASTRO | 3-day astronomy-oriented forecast bins: seeing, atmospheric transparency and related weather | provider terms explicitly allow software use without permission; no SPDX data licence stated | `LICENCIA NO VERIFICADA` in OSS taxonomy; `PRUEBA A/B` provider with explicit terms/provenance |
| OpenNGC | NGC/IC deep-sky catalog | CC-BY-SA-4.0 | `ALTERNATIVA OSS RECOMENDADA` for redistributable local catalog layer |
| SIMBAD / CDS | object IDs, measurements, bibliography | service declares ODbL / free access | `AUTHORITATIVE_DATABASE_COMPLEMENT` |
| VizieR / CDS | published catalogs | dataset-specific/source terms | `QUERY_COMPLEMENT`; verify per catalog |
| Gaia Archive / ESA | astrometric survey data | official archive; release-specific acknowledgement/terms | `PRIMARY_SURVEY_SOURCE` when needed |
| NASA/AAS solar-safety guidance | direct and magnified Sun viewing safety | authoritative guidance | `SAFETY_GATE_SOURCE` |
| Light-pollution map/provider | geographic sky-brightness/Bortle context | no automatic provider/API redistribution contract has been accepted for Centinela yet | `NO_AUTOMATIC_INGESTION`; accept measured SQM or explicitly source-labelled map-derived/user evidence until a provider is verified |

## Scientific-status rules

### Deterministic ephemeris calculation
Astronomy Engine output may support `HECHO_VERIFICADO` only when:
- observer/time/frame semantics are explicit;
- calculation is within documented scope;
- publication-critical event claims are cross-checked against an authoritative current source when required by Project policy.

Fixed J2000 targets supplied manually by a Product user remain `NO_VERIFICADO` until bound to a catalog/source. Local altitude/azimuth, darkness and Moon-separation calculations derived from those coordinates are therefore guidance over an unverified input, not a promotion of the input itself.

### Scientific HTTPS transport
Network data providers used by Observation Intelligence follow one explicit boundary:
- HTTPS only;
- exact host allowlist;
- bounded response size and timeout;
- final redirect host revalidated;
- JSON UTF-8 object required where JSON is expected;
- no hidden automatic retry loop;
- provider parser remains separate from transport;
- network access occurs only from an explicit caller action, never as a publication side effect.

Provider-specific rate/fair-use policies override generic convenience. Centinela must not turn a best-effort public science service into a high-frequency polling backend.

### Weather
Weather is always forecast/measurement evidence, not an astronomical fact.
- retain provider;
- retrieval timestamp;
- valid timestamp;
- model/run when available;
- stale state;
- no seeing/transparency inference from ordinary cloud/humidity fields unless a documented physical model is deliberately implemented and labelled `INFERENCIA`.

Open-Meteo remains the ordinary meteorological layer. It must not be presented as a seeing/transparency provider when those variables were not returned by the queried product.

### Astronomy-specific atmospheric forecasts
7Timer! ASTRO publishes seeing and atmospheric-transparency categories rather than exact continuous measurements. Centinela therefore preserves provider bins as bounded evidence:
- seeing categories retain lower/upper bounds in arcseconds;
- transparency categories retain extinction bounds in magnitudes per airmass;
- no midpoint is silently fabricated;
- open-ended worst bins are scored fail-closed rather than assigned an optimistic exact value;
- the canonical JSON response is SHA-256 bound into `source_id`;
- forecast init time, valid time and retrieval time remain distinct;
- these values remain `FORECAST`, never `HECHO_VERIFICADO`.

For a finite atmospheric-extinction upper bound `k`, Observation Intelligence may derive the conservative one-airmass transmission floor `T = 10^(-0.4 k)` as `INFERENCIA`. The original extinction bounds remain the source evidence.

### Bortle / sky brightness
Never infer Bortle class from locality name alone.
Distinguish:
- measured SQM;
- map-derived value;
- user-supplied estimate;
- inference.

SQM, Bortle and map-derived sky quality must not be silently converted into one another. Any explicit conversion model added later requires its own provenance, assumptions and scientific-status label.

An external light-pollution map may be useful for discovery, but Centinela will not scrape or automatically ingest it until the exact API/access, caching and redistribution terms are verified. Product input can still record a map-derived Bortle class when the user supplies an explicit source identifier; that remains `MAP_DERIVED`, not a measured SQM value.

### Deep-sky catalogs
Local OpenNGC data must retain:
- exact snapshot commit/hash;
- CC-BY-SA-4.0 attribution/license notice;
- original field semantics (J2000 RA/Dec, arcmin axes, magnitude bands);
- duplicate/nonexistent-record handling.

SIMBAD/VizieR may complement or resolve ambiguity but must not silently overwrite a pinned local value without provenance.

### Meteor showers
The IAU WG Meteor Shower Nomenclature identifies the IAU Meteor Data Center as the central repository and official shower database. Therefore:
- official shower identity/nomenclature should be anchored to the IAU MDC;
- future activity/peak/radiant/ZHR claims must retain the exact source and epoch/date context;
- radiant drift is applied only when an explicit drift plus reference epoch is supplied;
- ZHR is an idealized shower descriptor and is never converted by Centinela into a guaranteed/predicted local observed meteor count;
- local planning may rank radiant elevation, darkness and Moon interference as `INFERENCIA`;
- automated MDC bulk ingestion remains blocked until exact machine-readable format and redistribution terms are reviewed.

### Comets / asteroids / small bodies
Do not hard-code future claims without an authoritative data-update mechanism. Small-body observer ephemerides are delegated to JPL Horizons rather than propagated locally without an explicitly validated orbital model.

Current Horizons boundary:
- topocentric observer query uses `coord@399` + geodetic site coordinates;
- the API `signature.source` must identify NASA/JPL Horizons;
- the API `signature.version` must equal an explicitly reviewed version;
- Centinela currently pins the reviewed API documentation contract to `1.3` (2025 June) and fails closed on an unreviewed version;
- the single-time query must return exactly one labelled observer row;
- exact Horizons result text is SHA-256 bound into provenance;
- no unlabeled/duplicate CSV columns are silently accepted;
- the SSD/CNEOS fair-use policy requires only necessary requests, one request at a time, cache/reuse where practical, and appropriate handling of errors/rate limits rather than repetitive retry;
- API availability is best-effort and formats can change, so a provider failure must remain visible rather than being filled with invented ephemerides.

### Landscape / Milky Way planning
A fixed-J2000 target can be sampled through a local time window for altitude/azimuth, darkness and Moon separation. The resulting score is geometric `INFERENCIA` only. It does not claim:
- a clear real horizon;
- local weather at the exact field position unless forecast evidence is supplied;
- adequate light pollution unless sky-quality evidence is supplied;
- photographic success;
- foreground/compositional suitability.

### Solar safety
Solar safety is fail-closed. No LLM, AI visual, user preset or convenience feature can override the safety gate silently.

## Source acceptance checklist

Before adding a new astronomy source:
1. identify exact provider/dataset;
2. verify current licence/terms;
3. define whether data may be cached/redistributed;
4. define units/frame/epoch/timezone;
5. retain retrieval and validity timestamps where dynamic;
6. define stale/missing behavior;
7. add deterministic fixtures/adversarial tests;
8. map outputs to the scientific-status taxonomy;
9. ensure publication has no automatic side effect.

## Current deliberate non-implementations

These are not accidental omissions:
- no automatic scraping of a light-pollution website without verified API/redistribution terms;
- no automatic scraping/bulk redistribution of IAU MDC shower data before its exact access/licence contract is reviewed;
- no local comet/asteroid orbit propagation as a substitute for Horizons;
- no ZHR → local meteor-count formula presented as fact;
- no forecast retry storm or background polling loop;
- no scientific provider call coupled to automatic publication.

## Open-source classification vocabulary

Use only:
`OPEN SOURCE + 100 % GRATUITA / OSS CON SERVICIO DE PAGO / PESOS ABIERTOS / SOURCE AVAILABLE / FREEMIUM / COMERCIAL / LICENCIA NO VERIFICADA`.

Decisions:
`MANTENER / ALTERNATIVA OSS RECOMENDADA / NO COMPENSA / PRUEBA A/B / NO HAY ALTERNATIVA MEJOR VERIFICADA`.
