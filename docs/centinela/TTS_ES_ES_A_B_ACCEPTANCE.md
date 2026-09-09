# Centinela TTS ES-ES — A/B acceptance contract

Date: 2026-09-08

Status: specification only; no model download or local runtime certification is authorized by this document.

Permanent policy: `GENERAR → REVISAR → APROBAR → PUBLICAR` / `AUTO_PUBLICATION=FALSE`.

## Goal

Choose the highest-quality reasonable-cost narration path for **EL CENTINELA DEL UNIVERSO** on the physical Windows 11 / RTX 2060 6 GB / 16 GB RAM workstation, prioritizing Spanish from Spain, male narration, astronomy pronunciation, natural cinematic delivery, stability and zero/low cost.

A provider is not canonical because it is open source, popular or fast. It must win the same blinded content benchmark on the target PC.

## Current candidates

| Candidate | Current classification | Verified rationale | PC decision |
|---|---|---|---|
| Edge TTS | FREE ONLINE SERVICE / not local OSS | Existing MPT path; no API key; useful quality baseline | KEEP AS BASELINE |
| Qwen3-TTS 0.6B | OPEN SOURCE / Apache-2.0 | Official Qwen3-TTS supports Spanish; smaller released model | A/B |
| Qwen3-TTS 1.7B | OPEN SOURCE / Apache-2.0 | Higher-capacity candidate; may exceed practical RTX 2060 budget | A/B only if memory-safe |
| Chatterbox Spain Spanish pack | OPEN SOURCE / MIT code; model terms to recheck at download | Official Resemble AI repo exposes dedicated `Chatterbox-Multilingual-es-es` single-language pack | PRIORITY A/B |
| Chatterbox Multilingual V3 | OPEN SOURCE / MIT code | Official 500M multilingual model with Spanish | A/B fallback/reference |
| Kokoro-82M | OPEN/PERMISSIVE candidate; exact model/runtime terms recheck at download | Very small CPU-friendly upstream MPT candidate | A/B efficiency baseline |

Do not download multi-GB candidates without explicit user authorization.

## Mandatory test corpus

Run the exact same texts, punctuation and output settings for every candidate.

### A. Neutral scientific narration

`La Luna estará a unos treinta grados sobre el horizonte. Júpiter culminará más tarde, pero la nubosidad puede impedir la observación.`

### B. Spain-Spanish prosody

`Esta noche, desde Castilla y León, no necesitamos mirar deprisa. Esperaremos a que termine el crepúsculo astronómico y el cielo se oscurezca por completo.`

### C. Astronomy terminology

`Ascensión recta, declinación, azimut, eclíptica, perihelio, afelio, perigeo, apogeo y magnitud aparente describen propiedades diferentes.`

### D. Proper names

`Betelgeuse, Aldebarán, Antares, Rigel, Sirio, las Pléyades y la galaxia de Andrómeda aparecen en regiones distintas del cielo.`

### E. Catalog identifiers

`Messier treinta y uno, Messier cuarenta y dos, NGC siete mil e IC cuatrocientos treinta y cuatro son objetivos muy diferentes.`

### F. Numbers and units

`La distancia es de aproximadamente dos millones y medio de años luz, la exposición dura treinta segundos y la focal efectiva es de ochocientos milímetros.`

### G. Date and eclipse

`El doce de agosto de dos mil veintiséis ocurrió un eclipse total de Sol visible desde parte de España.`

### H. Cinematic restrained delivery

`El Sol desaparece. El horizonte conserva todavía un resplandor tenue. Minutos después, la noche revela un cielo que durante el día estaba oculto a nuestra vista.`

### I. Long-form stability

Use one continuous 90–150 second Centinela script containing scientific terminology, dates, units, proper nouns and narrative pauses.

### J. Adversarial text hygiene

Include repeated punctuation, parentheses, abbreviations, decimal numbers, `M31`, `NGC 7000`, `km/s`, `°`, and Unicode Spanish punctuation. The model must not hallucinate extra speech or silently omit scientific content.

## Blinded human scoring — 100 points

| Dimension | Weight |
|---|---:|
| Naturalness / absence of synthetic artifacts | 25 |
| Spain-Spanish accent suitability | 20 |
| Astronomy/proper-name pronunciation | 20 |
| Cinematic but restrained prosody | 15 |
| Long-form stability / no hallucination or omission | 10 |
| Resource use + latency on target PC | 5 |
| Timestamp/alignment usefulness | 5 |

### Critical fail conditions

A candidate cannot become canonical if any occurs repeatedly:
- obvious non-Spain accent when an ES-ES-specific alternative is available;
- invented words or omitted scientific claims;
- unstable long-form generation;
- OOM / severe swapping / workstation instability;
- licensing or redistribution status unresolved;
- output cannot be reliably aligned to the script without an acceptable timestamp strategy.

### Acceptance bands

- `>= 90`: canonical-quality candidate, subject to operational stability
- `85–89.99`: strong candidate; compare against current winner
- `75–84.99`: fallback only
- `< 75`: not selected for Centinela narration

No aggregate score can hide a critical fail condition.

## Machine metrics to capture

For each provider/model/voice:
- exact provider/model/version/hash where available;
- exact runtime and dependency versions;
- CPU/GPU path;
- peak system RAM;
- peak VRAM;
- generation wall time;
- generated audio duration;
- real-time factor (`generation_seconds / audio_seconds`);
- output sample rate/format;
- retry count and failures;
- whether native timestamps exist;
- alignment path used;
- whether Whisper/faster-whisper was required;
- any OOM/recovery behavior.

## Timestamp policy

1. Native TTS word/sentence timestamps when trustworthy.
2. Deterministic text/audio alignment if the TTS output supports it.
3. Forced alignment when justified.
4. Whisper/faster-whisper only when necessary, never automatically because it exists.

## Decision format

`PROVIDER | MODEL | VOICE | LICENSE | ES-ES SCORE | NATURALNESS | ASTRONOMY | RAM | VRAM | RTF | TIMESTAMPS | FAILURES | DECISION`

Possible decisions:
- `MANTENER`
- `ALTERNATIVA OSS RECOMENDADA`
- `PRUEBA A/B`
- `NO COMPENSA`
- `NO HAY ALTERNATIVA MEJOR VERIFICADA`

## Evidence hierarchy

Human listening decides voice quality; machine metrics decide operational suitability. Neither substitutes for the other.
