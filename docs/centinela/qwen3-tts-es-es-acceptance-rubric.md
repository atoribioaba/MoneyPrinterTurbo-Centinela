# Qwen3-TTS ES-ES acceptance rubric — Centinela V1

Date: 2026-08-30
Scope: predefine the local acceptance test so PC time is used for measurement, not test design.

## Target voice

- language/accent: Spanish (Spain)
- speaker: male
- character: documentary, cinematic, calm, precise
- objective: natural narration for astronomy without announcer exaggeration
- mastering target after synthesis: 48 kHz, around -16 LUFS integrated, LRA around 7, -1 dBTP

## Safety / authority

- approved script is textual authority;
- TTS may not rewrite scientific content;
- numeric values, signs, units and magnitudes must remain FactLock-consistent;
- pronunciation normalization may change spoken form but never semantic value;
- no cloud/API requirement is accepted as a hidden dependency for the local V1 profile.

## Acceptance matrix

| Dimension | Pass criterion | Evidence on PC |
|---|---|---|
| Naturalness | no obvious robotic cadence across a 45–60 s astronomy narration | human A/B review |
| ES-ES accent | consistently Spain-Spanish pronunciation, no unwanted accent drift | human review |
| Scientific pronunciation | astronomy lexicon understandable and repeatable | marked test script + audio |
| Numeric fidelity | all FactLock numbers/signs/units preserved | script/audio comparison |
| Proper nouns | target terms intelligible without semantic substitution | lexicon score |
| Timing | usable utterance/segment timestamps if exposed | timestamp artifact |
| Subtitle utility | timestamps sufficiently stable to prefer over Whisper where possible | alignment sample |
| Stability | repeated generation does not crash or corrupt output | repeated-run log |
| GPU path | actual accelerator use demonstrated if expected | runtime log / `nvidia-smi` evidence |
| VRAM | no OOM on RTX 2060 6 GB | peak evidence |
| RAM | no harmful system swapping on 16 GB RAM | peak evidence |
| Speed | measured end-to-end generation time for fixed script | timing log |
| Audio integrity | expected sample rate/channels, no clipping/corruption | ffprobe/audio check |
| Mastering | post-process reaches project loudness/true-peak target | loudness report |

## Astronomy pronunciation test set

The following set is intentionally broader than one video so the profile can be reused:

- Betelgeuse
- Aldebarán
- Rigel
- Sirio
- Vega
- Antares
- Polaris
- Capella
- Pléyades
- Orión
- Capricornus
- eclíptica
- equinoccio
- solsticio
- perihelio
- afelio
- perigeo
- apogeo
- ascensión recta
- declinación
- magnitud aparente
- magnitud absoluta
- diámetro angular
- segundo de arco
- unidad astronómica
- parsec
- año luz
- Júpiter
- Saturno
- Urano
- Neptuno
- Mercurio
- Venus
- Marte
- eclipse penumbral
- eclipse parcial
- eclipse total
- ocultación
- conjunción
- oposición
- elongación
- terminador lunar
- mar lunar
- cráter Tycho
- Mare Imbrium
- M31 / galaxia de Andrómeda
- M42 / nebulosa de Orión
- M57 / nebulosa del Anillo

## Fixed benchmark script requirements

The PC benchmark script must include:

1. at least one decimal with comma in Spanish;
2. one negative magnitude;
3. one distance in kilometres;
4. one angular value in degrees;
5. one UTC timestamp or calendar date;
6. several proper nouns from the lexicon;
7. one parenthetical-style explanatory phrase;
8. one short cinematic pause and one longer transition pause.

The exact scientific values must come from an approved FactLock fixture, not be invented for narration convenience.

## A/B procedure

Compare at minimum:

- A: current Qwen3-TTS selected local profile;
- B: one alternative profile/voice or Edge TTS reference only if network/service use is explicitly enabled for the comparison.

Score 1–5 for naturalness, accent, pronunciation, pacing and emotional fit. Numeric/scientific fidelity is binary PASS/FAIL and overrides aesthetic preference.

## Subtitle decision rule

1. If Qwen3-TTS produces reliable timestamps, use them as first source.
2. If timestamps are absent or insufficiently accurate, use faster-whisper for alignment.
3. The approved script remains textual authority; STT output must not silently replace approved wording.

## Stop conditions

- any numeric/sign/unit mutation;
- repeatable OOM;
- unstable/crashing runtime;
- unintelligible astronomy proper nouns after reasonable pronunciation normalization;
- hidden online dependency in the intended local profile.

## Result labels

- `QWEN3_TTS_LOCAL=PASS`
- `QWEN3_TTS_LOCAL=PASS_WITH_PRONUNCIATION_LEXICON`
- `QWEN3_TTS_LOCAL=FAIL`
- `TIMESTAMPS=PRIMARY`
- `TIMESTAMPS=FASTER_WHISPER_FALLBACK`

No result may be set before the real local run.
