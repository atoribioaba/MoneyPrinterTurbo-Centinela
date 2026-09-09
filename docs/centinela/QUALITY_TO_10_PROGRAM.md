# EL CENTINELA DEL UNIVERSO — Quality-to-10 program

Date: 2026-09-08
Base checkpoint: C20 `2c6267c8d9ad3d144ebe6db73189a34c63656ce0`

This program improves dimensions previously scored between 5 and 9. It does not turn cloud evidence into physical-PC certification.

## Scoring rule

A dimension reaches **10/10** only when all of the following are true:
1. the architecture/contract is explicit;
2. fail-closed behavior is tested;
3. provenance/licence semantics are defined where relevant;
4. the capability is wired into the canonical production path;
5. at least one real end-to-end use case succeeds;
6. human quality review passes where subjective quality matters;
7. no unresolved P0/P1 defect remains for that dimension.

A planner/model/UI alone can never score 10.

## 1. Astronomy general — previous 8.4

### Implemented in this branch
- first-class deep-sky object model;
- OpenNGC parser with J2000 RA/Dec, angular size, magnitudes, surface brightness, Messier aliases and source codes;
- duplicate/nonexistent catalog records fail closed;
- explicit OpenNGC CC-BY-SA-4.0 provenance contract;
- Observation Intelligence foundation;
- solar-viewing fail-closed safety gate.

### To reach 10
- pin an exact OpenNGC snapshot/hash and license notice;
- add SIMBAD/VizieR query adapter for live cross-identification, without silently overwriting local catalog values;
- add authoritative meteor-shower source + local radiant geometry;
- add dynamic comet orbital-element source + uncertainty labels;
- add Galactic Center/Milky Way planning;
- run known-case astronomy regressions against authoritative reference cases;
- demonstrate a real Centinela content project using each major class.

## 2. Observation astronomy — previous 6.3

### Implemented in this branch
- deterministic Kasten-Young airmass;
- great-circle angular separation;
- target altitude, darkness, Moon interference, cloud, transparency, seeing, wind, dew and sky-quality scoring surfaces;
- object-specific documented weights;
- explicit completeness score;
- missing data cannot masquerade as excellent conditions;
- Open-Meteo forecast parser with CC BY 4.0 attribution and no invented seeing/transparency;
- Bortle/SQM evidence model distinguishing measured/map-derived/inferred inputs.

### To reach 10
- choose and verify a seeing/transparency provider or measured-input path;
- add forecast staleness/model-run policy;
- add horizon-profile support;
- compute local target track over an observing window, not one instant only;
- add Moon-target separation directly from Astronomy Core positions;
- add light-pollution provider with verified redistribution terms;
- validate the score against real field sessions and tune weights transparently;
- Product UI must show components, missing inputs and provenance instead of one opaque number.

## 3. Astrophotography — previous 5.8

### Implemented in this branch
- Equipment/optical-train models;
- focal multipliers for reducers/Barlows;
- exact rectilinear horizontal/vertical/diagonal FOV;
- effective focal length and focal ratio;
- angular pixel scale;
- target fit fractions;
- seeing-based sampling classification explicitly marked approximate;
- framing notes that do not pretend catalog dimensions include faint extensions.

### To reach 10
- Equipment Registry persisted in ProjectManifest/user settings;
- camera/lens/telescope/binocular/smartphone presets entered from real user equipment;
- orientation-aware framing and mosaic planning;
- mount payload/tracking/guiding constraints;
- planetary/lunar lucky-imaging planner;
- deep-sky capture planner with calibration, dithering and guiding context;
- session timeline linked to Observation Intelligence;
- post-processing pipeline with provenance-preserving masters;
- real field validation from smartphone → binoculars → telescope → deep sky.

## 4. Video real-PC — previous 5

Cloud contract C19 remains strong. A 10 requires physical evidence:
- actual FFmpeg build/license captured;
- real `h264_nvenc` encode on RTX 2060;
- measured libx264 fallback;
- 1080x1920 VIDEO_BASE validation;
- independent 2160x3840 master rerender;
- independent 1080x1920 social rerender;
- frame rate, duration, audio state and pixel dimensions checked with ffprobe;
- visual review for crop/focal/relevance;
- RAM/VRAM/encode-time metrics retained in run manifest.

## 5. Voice/audio design — previous 8.7

### Improved in this branch
- rigorous ES-ES blinded A/B contract;
- astronomy-specific test corpus;
- human + machine scoring split;
- critical fail conditions;
- exact RAM/VRAM/RTF/timestamp metrics;
- priority A/B includes dedicated Chatterbox Spain-Spanish pack, Qwen3-TTS, Kokoro and Edge baseline;
- upstream non-finite voice-rate defect tracked for minimal backport.

### To reach 10
- apply/test finite-rate guard during RC reconciliation;
- run all authorized candidates on target PC;
- choose actual male ES-ES voice by blinded listening;
- validate long-form astronomy pronunciation;
- measure native timestamp quality before Whisper;
- loudness/mastering benchmark on real output;
- preserve selected model/version/voice in runtime evidence.

## 6. Voice/audio real — previous 5

Cannot honestly become 10 in cloud. Required evidence:
- real TTS generation;
- no OOM/severe swapping;
- stable long-form run;
- acceptable ES-ES male voice;
- timing/alignment evidence;
- mastering output;
- human acceptance.

## 7. UX/Product — previous 8.8

To reach 10:
- wire Observation Intelligence into `Cielo` with component explanations;
- wire Equipment/FOV into observing/capture planning;
- preserve scientific-status badges and uncertainty in every relevant surface;
- add explicit stale/missing-data states;
- accessibility pass: keyboard path, focus, contrast, labels, reduced motion;
- mobile human acceptance on the final RC rather than historical UI lineage;
- no duplicate authority between legacy WebUI and Product UI.

## 8. Physical Windows certification — previous 5

Cannot increase honestly before the PC. Required:
- read-only preflight first;
- storage medium proof for D:/E:;
- exact Python/uv/FFmpeg/NVIDIA runtime inventory;
- actual CUDA-use proof;
- actual NVENC proof;
- Unicode/accents/spaces path tests on physical storage;
- start/stop/restart/update/recovery drills;
- no destructive reconciliation before preserved evidence.

## 9. Repository governance — previous 6

Already improved by Issues #67/#68 and this isolated branch.

To reach 10:
- preserve local state first;
- reconcile local ↔ C20 by resulting contracts, not PR number;
- create exactly one V1 release-candidate lineage;
- integrate only required changes from this branch after tests;
- mark historical PRs as evidence/superseded after reconciliation;
- update Issue #5/#3 final status;
- move default branch only by explicit decision after Golden;
- tag/freeze only after F58 + human approval.

## 10. Backup/recovery — previous 7.5

To reach 10:
- define complete backup set;
- preserve committed SHA/refs + dirty/untracked/stash separately;
- hash configuration/evidence manifests without exposing secrets;
- record media index/sidecar hashes;
- record model/runtime inventories and exact lockfiles;
- restore into a new non-destructive location;
- prove pytest/import/startup/media-index read after restore;
- perform at least one real recovery drill before V1 freeze.

## 11. OSS/supply chain — previous 9.0 cloud

To reach 10:
- final Windows SBOM/inventory;
- exact FFmpeg configure/license;
- exact model/runtime licenses and hashes;
- selected TTS/LLM/AI Visual models only, not candidate lists;
- transitive dependency audit after final RC lock;
- secret scan and immutable Action pins re-run at RC SHA.

## Final 10/10 release rule

`CLOUD_DESIGN_10` and `LOCAL_RUNTIME_10` are separate claims.

The project reaches global 10/10 readiness only after:

`PC PREFLIGHT → PRESERVATION → RECONCILIATION → FULL WINDOWS TESTS → REAL MEDIA/HARDWARE → REAL GOLDEN → REVIEW 7/7 → FINAL OSS/SBOM → F58 → HUMAN FREEZE APPROVAL`.

`AUTO_PUBLICATION=FALSE` remains invariant.
