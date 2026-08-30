# C3 cloud OSS audit + provisional SBOM

Date: 2026-08-30
Branch: `centinela-cert/c3-f58-readiness-v0.1`
Scope: cloud/static evidence only. This document does **not** replace the final PC/local audit required before F58.

## Status

- `C3_DIRECT_DEPENDENCY_MANIFEST=CAPTURED`
- `C3_TRANSITIVE_SBOM=PENDING_RUNNER_EXECUTION`
- `C3_LICENSE_AUDIT=IN_PROGRESS`
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
| moviepy | 2.2.1 | video composition | primary-source verification in progress |
| streamlit | 1.59.1 | WebUI | primary-source verification in progress |
| streamlit-tour | 1.1.0 | WebUI tour | primary-source verification pending |
| edge-tts | 7.2.7 | optional/network TTS path | primary-source verification in progress |
| fastapi | 0.136.3 | API | primary-source verification in progress |
| uvicorn | 0.32.1 | ASGI runtime | primary-source verification pending |
| openai | 2.24.0 | API compatibility/client | primary-source verification pending |
| faster-whisper | 1.1.0 | subtitle/alignment fallback | primary-source verification pending |
| loguru | 0.7.3 | logging | primary-source verification pending |
| dashscope | 1.20.14 | optional provider client | primary-source verification pending |
| azure-cognitiveservices-speech | 1.41.1 | optional cloud speech | primary-source verification pending |
| redis | 5.2.0 | state/runtime integration | primary-source verification in progress |
| python-multipart | 0.0.27 | multipart API support | primary-source verification pending |
| pyyaml | 6.0.3 | YAML parsing | primary-source verification pending |
| requests | 2.33.1 | HTTP client | primary-source verification pending |
| packaging | 24.2 | packaging/version utilities | primary-source verification pending |
| socksio | 1.0.0 | SOCKS transport | primary-source verification pending |
| pydub | 0.25.1 | audio utilities | primary-source verification pending |
| audioop-lts | 0.2.2; Python >=3.13 | Python 3.13 audioop compatibility | primary-source verification pending |
| litellm | 1.86.2 | multi-provider LLM abstraction | mixed OSS/enterprise surfaces; exact used surface must be verified |
| google-genai | 2.11.0 | optional Google GenAI client | primary-source verification pending |
| astronomy-engine | 2.1.19 | astronomy calculations | primary-source verification pending |
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

## Preliminary license evidence captured on 2026-08-30

This section is intentionally conservative. A component is not marked `verified=true` for F58 until its exact package/repository/license mapping is recorded.

| Function | Current component | Classification | Free | License evidence | Decision | F58 verified |
|---|---|---|---:|---|---|---:|
| application core | MoneyPrinterTurbo-Centinela / MoneyPrinterTurbo 1.3.4 | OPEN SOURCE + 100 % GRATUITA | yes | repository declares MIT | MANTENER | yes |
| video composition | MoviePy | OPEN SOURCE + 100 % GRATUITA | yes | upstream project metadata declares MIT | MANTENER | provisional |
| TTS fallback | edge-tts | OSS client + external service | client yes | upstream metadata identifies LGPLv3; service behavior/terms are separate | keep only as fallback; local Qwen TTS preferred | provisional |
| Redis Python client | redis-py | OPEN SOURCE + 100 % GRATUITA | yes | upstream LICENSE identifies MIT | MANTENER | provisional |
| LLM abstraction | LiteLLM | OSS core + commercial/enterprise surfaces | core yes | upstream separates MIT-accessible code from enterprise-licensed surfaces | keep only used OSS surface; verify exact imports/features | provisional |

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

Repeat the inventory on the actual Windows V1 environment and additionally capture non-Python/runtime components: FFmpeg build/license flags, Ollama, Qwen model metadata/license, Qwen3-TTS, CUDA-dependent wheels/runtimes and NVIDIA/NVENC path.

## Fail-closed rules

- Unknown license => `LICENCIA NO VERIFICADA`, never inferred.
- Cloud provider client license != service usage rights.
- FFmpeg license must be read from the actual build; do not assume LGPL/GPL profile.
- Model weights license is audited separately from the runtime/code license.
- An OSS client around a paid API is classified `OSS CON SERVICIO DE PAGO` where applicable.
- F58 `oss_audit_complete` remains false until every entry passed to F58 has `verified=true`.
