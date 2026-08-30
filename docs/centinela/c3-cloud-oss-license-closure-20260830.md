# C3 cloud OSS license closure — 2026-08-30

Status: cloud/static closure for dependency licensing and provider classification. This is **not** the final local SBOM and does not authorize F58, merge, architecture freeze, or publication.

## Guardrails

- `CLOUD_STATIC_LICENSE_AUDIT=CLOSED_WITH_LOCAL_FINAL_GATES`
- `TRANSITIVE_INSTALLED_SBOM=LOCAL_OR_RUNNER_PENDING`
- `F58_OSS_AUDIT_COMPLETE=FALSE`
- `MERGE_AUTHORIZED=FALSE`
- `ARCHITECTURE_FREEZE_AUTHORIZED=FALSE`
- `AUTO_PUBLICATION=FALSE`

The authoritative dependency manifest remains `pyproject.toml`; exact runtime resolution remains `uv.lock`.

## Direct/runtime dependency license evidence

Evidence was checked against upstream repository metadata and/or the exact-version PyPI metadata available on 2026-08-30. Hosted-service terms are intentionally separated from Python-package licenses.

| Dependency | Requested version/spec | Package/license classification | V1 role decision | Final-local gate |
|---|---:|---|---|---|
| moviepy | 2.2.1 | MIT | core/local | installed artifact metadata |
| streamlit | 1.59.1 | Apache-2.0 | core/local WebUI | installed artifact metadata |
| streamlit-tour | 1.1.0 | BSD-3-Clause upstream project | WebUI support | exact installed artifact/source alignment |
| edge-tts | 7.2.7 | LGPLv3 client + external online service | fallback only; not local-primary TTS | installed artifact + service-use decision |
| fastapi | 0.136.3 | MIT | core/local API | installed artifact metadata |
| uvicorn | 0.32.1 | BSD-3-Clause | core/local API runtime | installed artifact metadata |
| openai | 2.24.0 | Apache-2.0 client + external paid/hosted API | provider compatibility only; not V1 local-primary | installed artifact; API use remains disabled unless explicitly selected |
| faster-whisper | 1.1.0 | MIT | local subtitle/alignment fallback | exact CTranslate2/CUDA/runtime graph |
| loguru | 0.7.3 | MIT | core utility | installed artifact metadata |
| dashscope | 1.20.14 | Apache-2.0 client + external Alibaba Cloud service | provider compatibility only; not V1 local-primary | installed artifact; service use requires explicit selection |
| azure-cognitiveservices-speech | 1.41.1 | proprietary Microsoft Speech SDK + external service | provider compatibility only; **not OSS** and not V1 local-primary | exact installed terms if retained; no cloud-service dependency required for V1 |
| redis | 5.2.0 | MIT | runtime integration if enabled | installed artifact metadata |
| python-multipart | 0.0.27 | Apache-2.0 | API support | installed artifact metadata |
| pyyaml | 6.0.3 | MIT | core utility | installed artifact metadata |
| requests | 2.33.1 | Apache-2.0 | HTTP utility | installed artifact metadata |
| packaging | 24.2 | Apache/BSD dual-license metadata | packaging utility | exact installed license files |
| socksio | 1.0.0 | MIT | transport support | installed artifact metadata |
| pydub | 0.25.1 | MIT | audio utility | installed artifact metadata |
| audioop-lts | 0.2.2; Python >=3.13 | PSF-2.0 | Python 3.13 compatibility only | exact platform wheel if Python 3.13 is used locally |
| litellm | 1.86.2 | MIT package; enterprise/commercial features separately licensed | use only verified OSS/core surface; local Ollama remains preferred V1 path | imported-feature audit + installed artifact |
| google-genai | 2.11.0 | Apache-2.0 client + external Google service | provider compatibility only; not V1 local-primary | installed artifact; service use requires explicit selection |
| astronomy-engine | 2.1.19 | MIT | local astronomy calculation | installed artifact metadata |
| tzdata | >=2025.3 | Apache-2.0 | timezone data | resolved installed version/source |

## Optional dependency

| Dependency | Requested spec | Classification | V1 decision |
|---|---:|---|---|
| twelvelabs | >=1.2.8 | optional SDK for external TwelveLabs platform; API key required; exact SDK license not established strongly enough from the inspected package/repository metadata | `OPTIONAL_NOT_SELECTED_FOR_LOCAL_V1`; keep out of default install path unless explicitly justified later |

This is deliberately fail-closed: the absence of strong exact-license evidence for the optional TwelveLabs SDK is recorded as `LICENCIA NO VERIFICADA`, not inferred.

## Development dependencies

| Dependency | Requested version | License | Decision |
|---|---:|---|---|
| coverage | 7.15.1 | Apache-2.0 | keep test tooling |
| pytest | 9.1.1 | MIT | keep test tooling |
| ruff | 0.15.21 | MIT | keep lint tooling |

## Hosted-provider classification

The following packages may be installed because MoneyPrinterTurbo supports several provider paths. Their presence in the dependency graph does **not** make those hosted services part of the Centinela V1 architecture.

| Integration | Client/package status | Hosted service status | Centinela V1 |
|---|---|---|---|
| OpenAI | Apache-2.0 Python SDK | external API; pricing/terms separate | compatibility only, not selected primary |
| DashScope | Apache-2.0 Python SDK | external Alibaba Cloud service | compatibility only, not selected primary |
| Google GenAI | Apache-2.0 Python SDK | external Google service | compatibility only, not selected primary |
| Azure Speech | proprietary SDK | external Microsoft service | not OSS; compatibility only, not selected primary |
| TwelveLabs | optional SDK, exact license not verified here | external video-understanding API | optional extra, not selected for local V1 |
| Edge TTS | LGPLv3 client | external Microsoft online TTS behavior/service | fallback only; Qwen3-TTS local remains preferred |
| LiteLLM | MIT package | can route to multiple external services; enterprise features separately licensed | only OSS/local-compatible surface if used |

No assumption is made that a ChatGPT, Google, Microsoft, Alibaba, or other consumer subscription includes API usage.

## SBOM generator decision

### Primary V1 choice: CycloneDX Python

- Tool/package: `cyclonedx-bom` / CLI `cyclonedx-py`.
- Cloud-verified release for the prepared contract: `7.3.1`.
- License: Apache-2.0.
- Reason: designed to generate CycloneDX SBOMs from an actual Python/virtual environment, including dependency graph and licenses; this matches the Windows-native + `uv` V1 architecture.
- Intended input on GitHub/PC: the environment created by `uv sync --frozen` from the checked-in `uv.lock`.
- Intended output: reproducible CycloneDX JSON plus a plain resolved-package inventory.

### Secondary candidate: Syft

Syft is Apache-2.0 and useful for whole-filesystem/non-Python inventory. It is **not required for V1 freeze** because adding another binary would not improve the primary Python dependency evidence enough to justify the extra moving part. Keep it as a later cross-check if non-Python coverage becomes necessary.

Decision: `cyclonedx-bom 7.3.1 = ALTERNATIVA OSS RECOMENDADA / PRIMARY SBOM GENERATOR FOR V1`.

## Exact evidence that remains local or runner-dependent

The cloud/static license audit cannot close these facts:

1. full transitive package graph actually installed by `uv sync --frozen`;
2. exact wheel/source hashes and package license files in the real Windows environment;
3. actual FFmpeg build configuration and resulting LGPL/GPL mode;
4. actual Ollama version and local Qwen3.5 model digest/quantization;
5. exact Qwen3-TTS code/model artifact, revision, hash and license files;
6. exact faster-whisper/CTranslate2/CUDA runtime combination;
7. any exact CLIP/Florence weights selected by the final SmartFocal path;
8. RAM/VRAM/runtime measurements.

## F58 consequence

Cloud licensing work is no longer a reason to redesign the V1 stack. F58 must nevertheless keep `oss_audit_complete=false` until the machine-readable transitive SBOM and the exact local runtime/model evidence are captured and every final audit row is `verified=true`.
