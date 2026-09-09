# Centinela astronomy source registry

Date: 2026-09-09

This registry separates deterministic calculation libraries, data providers, catalogs, forecasts and safety authorities. A source being open or authoritative does not make every derived statement a `HECHO_VERIFICADO`.

| Source | Role | Current licence/status | Centinela decision |
|---|---|---|---|
| Astronomy Engine (`cosinekitty/astronomy`) | deterministic solar-system calculations | MIT | `MANTENER` |
| NASA Science | eclipses / missions / solar safety / primary public science context | U.S. government/public-source terms vary by asset | `PRIMARY_AUTHORITY` |
| ESA | missions / discoveries / spacecraft science | official source; asset terms per item | `PRIMARY_AUTHORITY` |
| IGN España | official Spanish astronomical/geographic context where applicable | official source; terms per dataset/page | `PRIMARY_AUTHORITY_ES` |
| IAU | nomenclature / standards / astronomical authority | official body | `PRIMARY_AUTHORITY` |
| Open-Meteo | ordinary meteorological forecasts | API data CC BY 4.0; server AGPLv3 | `OSS CON SERVICIO DE PAGO`; free/open-data use with attribution where applicable |
| 7Timer! ASTRO | 3-day astronomy-oriented forecast bins: seeing, atmospheric transparency and related weather | provider terms explicitly allow software use without permission; no SPDX data licence stated | `LICENCIA NO VERIFICADA` in OSS taxonomy; `PRUEBA A/B` provider with explicit terms/provenance |
| OpenNGC | NGC/IC deep-sky catalog | CC-BY-SA-4.0 | `ALTERNATIVA OSS RECOMENDADA` for redistributable local catalog layer |
| SIMBAD / CDS | object IDs, measurements, bibliography | service declares ODbL / free access | `AUTHORITATIVE_DATABASE_COMPLEMENT` |
| VizieR / CDS | published catalogs | dataset-specific/source terms | `QUERY_COMPLEMENT`; verify per catalog |
| Gaia Archive / ESA | astrometric survey data | official archive; release-specific acknowledgement/terms | `PRIMARY_SURVEY_SOURCE` when needed |
| NASA/AAS solar-safety guidance | direct and magnified Sun viewing safety | authoritative guidance | `SAFETY_GATE_SOURCE` |

## Scientific-status rules

### Deterministic ephemeris calculation
Astronomy Engine output may support `HECHO_VERIFICADO` only when:
- observer/time/frame semantics are explicit;
- calculation is within documented scope;
- publication-critical event claims are cross-checked against an authoritative current source when required by Project policy.

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

### Deep-sky catalogs
Local OpenNGC data must retain:
- exact snapshot commit/hash;
- CC-BY-SA-4.0 attribution/license notice;
- original field semantics (J2000 RA/Dec, arcmin axes, magnitude bands);
- duplicate/nonexistent-record handling.

SIMBAD/VizieR may complement or resolve ambiguity but must not silently overwrite a pinned local value without provenance.

### Comets / meteors / transient events
Do not hard-code future claims without an authoritative data-update mechanism. Required future adapters must retain epoch, orbital/data source and prediction uncertainty. Small-body observer ephemerides are delegated to JPL Horizons rather than locally propagated without an explicitly validated orbital model.

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

## Open-source classification vocabulary

Use only:
`OPEN SOURCE + 100 % GRATUITA / OSS CON SERVICIO DE PAGO / PESOS ABIERTOS / SOURCE AVAILABLE / FREEMIUM / COMERCIAL / LICENCIA NO VERIFICADA`.

Decisions:
`MANTENER / ALTERNATIVA OSS RECOMENDADA / NO COMPENSA / PRUEBA A/B / NO HAY ALTERNATIVA MEJOR VERIFICADA`.
