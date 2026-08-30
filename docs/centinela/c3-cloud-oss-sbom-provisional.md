# C3 cloud OSS audit + provisional SBOM

Date: 2026-08-30
Branch: `centinela-cert/c3-f58-readiness-v0.1`
Scope: cloud/static evidence only. This document does **not** replace the final PC/local audit required before F58.

## Status

- `C3_DIRECT_DEPENDENCY_MANIFEST=CAPTURED`
- `C3_TRANSITIVE_SBOM=PENDING_RUNNER_EXECUTION`
- `C3_ACTIVE_PIPELINE_LICENSE_AUDIT=SUBSTANTIALLY_VERIFIED_CLOUD_SIDE`
- `F58_OSS_AUDIT_COMPLETE=FALSE`
- `LOCAL_RUNTIME_LICENSE_CONFIRMATION_REQUIRED=TRUE`
- `AUTO_PUBLICATION=FALSE`
- `ARCHITECTURE_FREEZE_AUTHORIZED=FALSE`

## Repository metadata verified from `pyproject.toml`

- Project: `moneyprinterturbo`
- Version: `1.3.4`
- Python: `>=3.11`
- Project license declaration: `MIT`
- Runtime resolution authority: `uv.lock`

## Direct dependency manifest

| Dependency | Requested version/spec | Role / note | License audit status |
|---|---:|---|---|
| moviepy | 2.2.1 | video composition | MIT verified upstream |
| streamlit | 1.59.1 | WebUI | Apache-2.0 verified upstream |
| streamlit-tour | 1.1.0 | WebUI tour | primary-source verification pending |
| edge-tts | 7.2.7 | optional/network TTS path | client LGPLv3 verified upstream; service terms separate |
| fastapi | 0.136.3 | API | MIT verified upstream |
| uvicorn | 0.32.1 | ASGI runtime | BSD-3-Clause corroborated; exact package source to capture in final SBOM |
| openai | 2.24.0 | API compatibility/client | optional provider client; final service/SDK classification pending |
| faster-whisper | 1.1.0 | subtitle/alignment fallback | MIT verified project family; exact installed dependency graph pending |
| loguru | 0.7.3 | logging | primary-source verification pending |
| dashscope | 1.20.14 | optional provider client | service/SDK audit pending |
| azure-cognitiveservices-speech | 1.41.1 | optional cloud speech | service/SDK audit pending |
| redis | 5.2.0 | state/runtime integration | MIT verified upstream |
| python-multipart | 0.0.27 | multipart API support | primary-source verification pending |
| pyyaml | 6.0.3 | YAML parsing | primary-source verification pending |
| requests | 2.33.1 | HTTP client | primary-source verification pending |
| packaging | 24.2 | packaging/version utilities | primary-source verification pending |
| socksio | 1.0.0 | SOCKS transport | primary-source verification pending |
| pydub | 0.25.1 | audio utilities | primary-source verification pending |
| audioop-lts | 0.2.2; Python >=3.13 | Python 3.13 audioop compatibility | primary-source verification pending |
| litellm | 1.86.2 | multi-provider LLM abstraction | OSS core + enterprise/commercial surfaces; used surface must stay OSS-verified |
| google-genai | 2.11.0 | optional Google GenAI client | service/SDK audit pending |
| astronomy-engine | 2.1.19 | astronomy calculations | MIT verified upstream |
| tzdata | >=2025.3 | timezone database | primary-source verification pending |

### Optional dependency

| Dependency | Requested version/spec | Role | Status |
|---|---:|---|---|
| twelvelabs | >=1.2.8 | optional video understanding/embedding | not part of default install unless extra configured; license/service terms require separate audit |

### Development dependencies

| Dependency | Requested version | Role | Status |
|---|---:|---|---|
| coverage | 7.15.1 | coverage | audit pending |
| pytest | 9.1.1 | tests | audit pending |
| ruff | 0.15.21 | lint | audit pending |

## Verified active-pipeline OSS evidence — cloud side

The following entries are based on upstream project/model license declarations checked on 2026-08-30. `cloud verified` means the upstream license identity is verified; exact local binary/model/version provenance can still remain pending.

| Function | Current / candidate | Classification | Free | License | Cloud verification | V1 decision |
|---|---|---|---:|---|---|---|
| application core | MoneyPrinterTurbo-Centinela / MPT 1.3.4 | OPEN SOURCE + 100 % GRATUITA | yes | MIT | repository verified | MANTENER |
| environment/package manager | uv | OPEN SOURCE + 100 % GRATUITA | yes | MIT OR Apache-2.0 | upstream verified | MANTENER |
| local LLM runtime | Ollama | OPEN SOURCE + 100 % GRATUITA | yes | MIT | upstream verified | MANTENER for V1 |
| alternate local LLM runtime | llama.cpp | OPEN SOURCE + 100 % GRATUITA | yes | MIT | upstream verified | ALTERNATIVA OSS / A-B only if useful |
| local LLM model family | Qwen3.5 4B | PESOS ABIERTOS | yes | Apache-2.0 | official model card verified | MANTENER baseline; exact local quantization/hash pending PC |
| deferred model | Qwen3.8 27B | PESOS ABIERTOS | yes | Apache-2.0 | official model card verified | PRUEBA A/B DIFERIDA; poor V1 hardware fit |
| local TTS code/model family | Qwen3-TTS | OPEN SOURCE / PESOS ABIERTOS | yes | Apache-2.0 | official code + 1.7B model family verified | MANTENER candidate; exact local model/perf pending PC |
| TTS fallback client | edge-tts | OSS CON SERVICIO EXTERNO | client yes | LGPLv3 client | client verified; service rights separate | fallback only |
| STT/alignment fallback | faster-whisper | OPEN SOURCE + 100 % GRATUITA | yes | MIT | project license verified | MANTENER fallback; local CUDA/runtime pending |
| video composition | MoviePy | OPEN SOURCE + 100 % GRATUITA | yes | MIT | upstream metadata verified | MANTENER |
| encoder/transcoder | FFmpeg | OPEN SOURCE | yes | LGPL-2.1+ base; can become GPL with enabled components | upstream license model verified | MANTENER; actual Windows build/license pending PC |
| WebUI | Streamlit | OPEN SOURCE + 100 % GRATUITA | yes | Apache-2.0 | upstream verified | MANTENER V1 |
| API | FastAPI | OPEN SOURCE + 100 % GRATUITA | yes | MIT | upstream verified | MANTENER |
| astronomy calculations | Astronomy Engine | OPEN SOURCE + 100 % GRATUITA | yes | MIT | upstream verified | MANTENER |
| visual analysis | OpenCV | OPEN SOURCE + 100 % GRATUITA | yes | Apache-2.0 for current releases | upstream verified | MANTENER where used |
| conceptual image matching | OpenAI CLIP code | OPEN SOURCE + 100 % GRATUITA | code yes | MIT code | upstream code verified; exact weights/license mapping must be captured if used | MANTENER SUPPORT ROLE only |
| spatial vision | Florence-2 family | PESOS/IMPLEMENTATION TO VERIFY EXACTLY | unknown until exact artifact | code/repo variants include MIT | family evidence insufficient for final exact artifact | MANTENER SUPPORT ROLE only after exact-model license capture |
| LLM abstraction | LiteLLM | OSS CORE + COMMERCIAL/ENTERPRISE SURFACES | core yes | MIT-accessible core; enterprise surfaces separately licensed | upstream split verified | use only proven OSS surface |
| Redis client | redis-py | OPEN SOURCE + 100 % GRATUITA | yes | MIT | upstream verified | MANTENER if required |

## Service/API separation

The presence of an OSS Python client does not make the hosted service free/open-source. For V1 cost/privacy decisions:

- OpenAI SDK/API: client license and API pricing/terms are separate; do not assume ChatGPT subscription includes API usage.
- Google GenAI client/API: client license and service pricing/terms are separate.
- DashScope client/service: separate.
- Azure Speech SDK/service: separate.
- TwelveLabs client/service: separate and optional.
- edge-tts client: OSS client, but the Microsoft online TTS service is an external dependency.

Default local V1 should not depend on any paid/online provider unless explicitly selected later.

## Pipeline OSS audit required by F58

The final table must use the canonical columns:

`Función | Actual | Mejor candidato OSS | Gratuito | Licencia | VRAM/RAM | Mejora | Decisión`

Minimum functions to close before freeze:

1. Python/environment/runtime (`uv`).
2. LLM runtime (`Ollama` / candidate `llama.cpp`).
3. Local LLM/model (`qwen3.5:4b-q4_K_M`; Qwen3.8 A/B deferred).
4. TTS (`Qwen3-TTS`; Edge TTS fallback).
5. STT/alignment (`faster-whisper`).
6. Video composition (`MoviePy`).
7. Encode (`FFmpeg`, `h264_nvenc`, `libx264`).
8. WebUI (`Streamlit`).
9. API (`FastAPI`/Uvicorn).
10. SmartFocal/vision stack actually imported by V1.
11. Astronomy calculations (`astronomy-engine`).
12. Optional provider integrations that remain enabled in V1.

## SBOM strategy

### Cloud provisional

The direct manifest above is authoritative for direct requirements because it is copied from the branch `pyproject.toml`.

### Cloud full/transitive

When GitHub Actions runner execution is restored:

1. `uv sync --frozen` using the checked-in `uv.lock`.
2. export an exact resolved package inventory from that environment;
3. capture name, version, package source and license metadata;
4. produce machine-readable SBOM artifact (CycloneDX or SPDX preferred);
5. retain the artifact with the C3 evidence bundle.

### Local final on 2026-09-09+

Repeat the inventory on the actual Windows V1 environment and additionally capture non-Python/runtime components: FFmpeg build/license flags, Ollama, exact Qwen model/quantization metadata, exact Qwen3-TTS model, CUDA-dependent wheels/runtimes and NVIDIA/NVENC path.

## What can still be completed without the PC

- verify remaining active direct dependency licenses from primary package repositories;
- classify every optional online-provider SDK as `not selected`, `optional`, or `required` for local V1;
- prepare SBOM generator/CI contract for execution when runners recover;
- capture exact vision model artifact/license if Florence/CLIP weights are actually selected in the cloud code path.

## What must remain local-final

- actual installed package graph;
- actual FFmpeg configuration and resulting license mode;
- exact Ollama version and model digest;
- exact Qwen quantization/hash;
- exact Qwen3-TTS model/hash;
- exact faster-whisper/CTranslate2/CUDA runtime combination;
- RAM/VRAM measurements.

## Fail-closed rules

- Unknown license => `LICENCIA NO VERIFICADA`, never inferred.
- Cloud provider client license != service usage rights.
- FFmpeg license must be read from the actual build; do not assume LGPL/GPL profile.
- Model weights license is audited separately from the runtime/code license.
- An OSS client around a paid API is classified `OSS CON SERVICIO DE PAGO` where applicable.
- F58 `oss_audit_complete` remains false until every entry passed to F58 has `verified=true`.
