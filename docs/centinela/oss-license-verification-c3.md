# C3 OSS License Verification — Cloud Evidence

Date: 2026-08-30
Scope: components and direct dependencies relevant to the selected V1/cloud certification path.

This document records license evidence that can be verified without the Windows workstation. It deliberately does **not** claim the exact local FFmpeg build, NVIDIA driver/NVENC runtime, installed Python environment or model file hashes.

## Verified components

| Component | Role | License / classification | Cloud decision |
|---|---|---|---|
| MoneyPrinterTurbo 1.3.4 | Core application | MIT (repository metadata) | MANTENER |
| uv | Python/project manager | Apache-2.0 OR MIT | MANTENER |
| redis-py | Redis client | MIT | MANTENER if selected runtime uses Redis |
| Loguru | Logging | MIT | MANTENER |
| Pydantic | Contracts/models | MIT | MANTENER |
| FastAPI | API | MIT | MANTENER |
| Uvicorn | ASGI runtime | BSD license | MANTENER |
| BeautifulSoup4 | Parsing | MIT | MANTENER where required |
| MoviePy | Media composition support | MIT | MANTENER where current pipeline still uses it |
| Pydub | Audio utilities | MIT | MANTENER |
| Streamlit | V1 WebUI | Apache-2.0 | MANTENER |
| Pillow 10.4.0 | Image processing | HPND | MANTENER |
| Watchdog 4.0.1 | File watching | Apache-2.0 | MANTENER if runtime/WebUI requires it |
| cloudpathlib | Cloud path utility | MIT | MANTENER if required |
| LiteLLM 1.74.15 | Provider abstraction | MIT for package | KEEP ONLY IF IT EARNS ITS COMPLEXITY; external providers remain separate services |
| Proglog 0.1.12 | Progress logging | MIT | MANTENER where required |
| Tomli 2.0.1 | TOML parsing | MIT | TOOLING/RUNTIME SUPPORT |
| Setuptools 80.9.0 | Packaging | MIT | TOOLING |
| Wheel 0.45.1 | Packaging | MIT | TOOLING |
| SRT Equalizer 0.1.10 | Subtitle line shaping | MIT | KEEP ONLY IF needed after TTS timestamp/faster-whisper decision |
| PycURL 7.45.3 | libcurl binding | dual LGPL / MIT-derived | REVIEW ACTUAL USAGE |
| Playwright 1.54.0 | UI/browser testing | Apache-2.0 | MANTENER for visual/UI certification |
| Astronomy Engine | astronomy calculations | MIT | MANTENER if current scientific path depends on it |
| Ollama | Local LLM runtime | MIT | MANTENER pending local RTX/performance evidence |
| llama.cpp | Alternative LLM runtime | MIT | PRUEBA A/B / fallback |
| Qwen3.5-4B | Local LLM model | Apache-2.0 | MANTENER pending local evidence |
| Qwen3-TTS | Local TTS code/models reviewed | Apache-2.0 | MANTENER / PRUEBA A/B model size pending local quality/perf |
| faster-whisper | STT/alignment | MIT | MANTENER fallback |
| Whisper | STT reference | MIT code/weights | FALLBACK/COMPARISON |
| OpenCLIP | Semantic vision | MIT | PRUEBA A/B |
| Florence-2 | Spatial vision | MIT | PRUEBA A/B |
| Real-ESRGAN | Upscaling | BSD-3-Clause | PRUEBA A/B only; never automatic |
| MusicGen | Music generation candidate | code MIT; reviewed weights CC-BY-NC-4.0 | NO COMPENSA for monetized production |

## Video encoder licensing remains intentionally local-blocked

### FFmpeg

General upstream rule is LGPL-2.1+ under default configuration; enabling GPL components changes the effective licensing obligations. Therefore the final V1 record must inspect the **actual local binary/configure flags** rather than infer from upstream defaults.

Current decision: `MANTENER`.

Final verification on PC must capture:

- `ffmpeg -version`
- configure flags
- license line/build provenance
- `h264_nvenc` availability
- `libx264` availability

### NVENC

NVENC depends on NVIDIA proprietary driver/SDK functionality. It is a performance path, not an OSS component. It remains acceptable as the preferred encoder on the owned RTX 2060 only if the local smoke is stable. The open-source-oriented fallback is FFmpeg + libx264, whose presence may make the concrete FFmpeg build GPL-enabled and therefore must be documented exactly.

Current decision: `MANTENER NVENC + mandatory libx264 fallback`, pending local evidence.

## OSS SDK vs external service rule

An OSS Python SDK does **not** make its external API/service free, local or open source. Therefore the presence of packages such as OpenAI, Azure Speech, Google GenAI, DashScope, boto3, MSAL or other provider SDKs in `pyproject.toml` is not evidence that those services are selected for V1.

For the zero-cost/local-first V1 architecture, external-service SDKs are classified as optional integrations unless explicitly selected later after cost/privacy/licensing review.

## Evidence sources checked in cloud research

- redis-py official LICENSE / package metadata — MIT
- Loguru 0.7.2 PyPI — MIT
- Pydantic 2.11.5 official/PyPI — MIT
- Uvicorn 0.35.0 PyPI — BSD
- BeautifulSoup4 PyPI — MIT
- Pydub 0.25.1 PyPI — MIT
- Streamlit 1.45.0 PyPI — Apache-2.0
- Pillow 10.4.0 PyPI — HPND
- Watchdog 4.0.1 PyPI — Apache-2.0
- FastAPI 0.116.1 PyPI — MIT
- MoviePy PyPI — MIT
- Playwright 1.54.0 PyPI — Apache-2.0
- Astronomy Engine PyPI — MIT
- LiteLLM 1.74.15 PyPI — MIT
- SRT Equalizer 0.1.10 PyPI — MIT
- Proglog 0.1.12 PyPI — MIT
- Tomli 2.0.1 PyPI — MIT
- Setuptools PyPI — MIT
- Wheel 0.45.1 PyPI — MIT
- PycURL 7.45.3 PyPI — LGPL/MIT dual
- uv official repository — Apache-2.0 OR MIT

## Items not promoted to VERIFIED in this cloud pass

- `streamlit-player`: PyPI metadata inspected but license not explicitly surfaced in the evidence used here.
- `cchardet`: source references COPYING but the exact effective license was not established from the fetched evidence.
- `imagemagick==0.1.3`: package identity/licensing and actual dependence on an external ImageMagick executable require a separate review.
- optional cloud/provider SDKs: package licenses can be verified later, but they are not canonical local V1 components and do not block the selected pipeline audit.

These remain explicit audit findings; they are not silently treated as OSS-certified.
