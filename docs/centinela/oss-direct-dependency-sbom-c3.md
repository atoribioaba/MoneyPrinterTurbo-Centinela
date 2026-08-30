# C3 Provisional Direct-Dependency SBOM

Date: 2026-08-30
Source of package/version inventory: repository `pyproject.toml` on C3 branch.
Purpose: save workstation time by separating package inventory from final local runtime/license verification.

Legend:
- `VERIFIED`: license/classification verified in C3 research or repository metadata.
- `PENDING_VERIFY`: package/version is known from `pyproject.toml`, but its exact license has not yet been verified in this audit.
- `OPTIONAL_API`: SDK may be OSS while the external service is not a local OSS runtime dependency.

| Package / version | V1 role | License audit state | V1 decision | Local check required |
|---|---|---|---|---:|
| MoneyPrinterTurbo 1.3.4 | Core application | MIT / VERIFIED from project metadata | MANTENER | Yes, exact local lineage |
| redis 6.4.0 | Queue/state support | PENDING_VERIFY | MANTENER if used by selected runtime path | Yes |
| loguru 0.7.2 | Logging | PENDING_VERIFY | MANTENER | No special hardware check |
| requests 2.32.5 | HTTP client | PENDING_VERIFY | MANTENER | No |
| pydantic 2.11.5 | Models/contracts | PENDING_VERIFY | MANTENER | No |
| moviepy 2.2.1 | Media composition support | MIT / VERIFIED | MANTENER where still used | Render smoke |
| fastapi 0.116.1 | API | MIT / VERIFIED | MANTENER | API smoke |
| uvicorn 0.35.0 | ASGI runtime | PENDING_VERIFY | MANTENER | API smoke |
| beautifulsoup4 4.12.3 | Parsing | PENDING_VERIFY | MANTENER only where required | No |
| edge-tts 7.2.3 | TTS fallback | LGPL-3.0 family / VERIFIED at project level; online service dependency | FALLBACK, not principal | Network/service behavior if retained |
| pydub 0.25.1 | Audio utilities | PENDING_VERIFY | MANTENER if used | FFmpeg integration |
| streamlit 1.45.0 | V1 WebUI | Apache-2.0 / VERIFIED | MANTENER | Local WebUI smoke |
| streamlit-player 0.1.5 | WebUI player | PENDING_VERIFY | MANTENER if required | UI smoke |
| openai 1.65.1 | Optional API SDK | PENDING_VERIFY / OPTIONAL_API | NOT REQUIRED for zero-cost local V1 | No unless explicitly enabled |
| azure-cognitiveservices-speech 1.43.0 | Optional speech service SDK | PENDING_VERIFY / OPTIONAL_API | NOT PRINCIPAL | No unless explicitly enabled |
| google-generativeai 0.8.5 | Optional API SDK | PENDING_VERIFY / OPTIONAL_API | NOT REQUIRED for zero-cost local V1 | No unless explicitly enabled |
| google-genai 1.30.0 | Optional API SDK | PENDING_VERIFY / OPTIONAL_API | NOT REQUIRED for zero-cost local V1 | No unless explicitly enabled |
| dashscope 1.25.2 | Optional API SDK | PENDING_VERIFY / OPTIONAL_API | NOT REQUIRED for local V1 | No unless explicitly enabled |
| g4f 0.3.8.1 | Alternate provider integration | PENDING_VERIFY | DO NOT FIX AS CANONICAL V1 COMPONENT | No |
| jieba 0.42.1 | Tokenization/text | PENDING_VERIFY | MANTENER if dependency path requires it | No |
| pillow 10.4.0 | Image processing | PENDING_VERIFY | MANTENER | Image/render smoke |
| imagemagick 0.1.3 | ImageMagick Python integration | PENDING_VERIFY | REVIEW ACTUAL USAGE | Local executable/path if used |
| cloudpathlib 0.18.1 | Cloud path utility | PENDING_VERIFY | MANTENER if required | No |
| litellm 1.74.15 | LLM provider abstraction | MIT / VERIFIED | KEEP ONLY IF IT EARNS ITS COMPLEXITY | Local/provider smoke |
| proglog 0.1.12 | Progress logging | PENDING_VERIFY | MANTENER if transitively needed | No |
| watchdog 4.0.1 | File watching | PENDING_VERIFY | MANTENER if WebUI/runtime needs it | Local FS smoke |
| tomli 2.0.1 | TOML support | PENDING_VERIFY | MANTENER | No |
| setuptools 80.9.0 | Packaging | PENDING_VERIFY | TOOLING | No |
| srt-equalizer 0.1.10 | Subtitle utilities | PENDING_VERIFY | REVIEW VS TTS TIMESTAMPS/FWHISPER PATH | Subtitle smoke |
| pycurl 7.45.3 | HTTP/libcurl binding | PENDING_VERIFY | REVIEW ACTUAL USAGE | Windows build/runtime smoke |
| pysocks 1.7.1 | Proxy support | PENDING_VERIFY | OPTIONAL | No |
| wheel 0.45.1 | Packaging | PENDING_VERIFY | TOOLING | No |
| boto3 1.40.15 | AWS SDK | PENDING_VERIFY / OPTIONAL_API | NOT REQUIRED for local V1 | No unless enabled |
| uuid 1.30 | UUID package | PENDING_VERIFY | REVIEW NECESSITY vs stdlib | No |
| cchardet 2.1.7 | Charset detection | PENDING_VERIFY | REVIEW ACTUAL USAGE | Windows/Python compatibility smoke |
| playwright 1.54.0 | UI/browser testing | Apache-2.0 / PENDING FINAL VERIFICATION | MANTENER for visual/UI tests | Browser install/runtime |
| astronomy-engine >=2.1.19 | Astronomy calculations | PENDING_VERIFY | MANTENER if current FactLock/research path depends on it | Scientific regression |
| msal 1.33.0 | Microsoft auth SDK | PENDING_VERIFY / OPTIONAL_API | OPTIONAL | No unless OneDrive path enabled |
| onedrivesdk <2 | OneDrive integration | PENDING_VERIFY / OPTIONAL_API | OPTIONAL / REVIEW | No unless enabled |
| pyperclip 1.9.0 | Clipboard utility | PENDING_VERIFY | OPTIONAL | Windows smoke if used |

## Non-pyproject components already audited

| Function | Component | License/classification | Decision | Local proof pending |
|---|---|---|---|---:|
| Local LLM runtime | Ollama | MIT | MANTENER | Yes: RTX/RAM/perf |
| Alternate LLM runtime | llama.cpp | MIT | PRUEBA A/B / fallback | Yes if adopted |
| Local LLM model | Qwen3.5-4B | Apache-2.0 | MANTENER | Yes |
| TTS | Qwen3-TTS | Apache-2.0 code/models reviewed | MANTENER / A-B model size | Yes |
| STT/alignment | faster-whisper | MIT | MANTENER fallback | Yes if invoked |
| STT reference | Whisper | MIT code/weights | FALLBACK/COMPARISON | Optional |
| Video/audio | FFmpeg | LGPL-2.1+ default; exact build can differ | MANTENER | **Yes: exact build/license/features** |
| GPU encoder | NVENC through FFmpeg | build/hardware dependent | MANTENER with libx264 fallback | **Yes: RTX 2060** |
| Semantic vision | OpenCLIP | MIT | PRUEBA A/B | Resource/perf if enabled |
| Spatial vision | Florence-2 | MIT | PRUEBA A/B | Resource/perf if enabled |
| Upscaling | Real-ESRGAN | BSD-3-Clause | PRUEBA A/B only, never automatic | Resource/perf |
| Music generation | MusicGen | code MIT; reviewed weights CC-BY-NC-4.0 | NO COMPENSA for monetized production | No download planned |

## Remaining SBOM work before freeze

1. Verify licenses for remaining direct dependencies marked `PENDING_VERIFY`.
2. Generate a machine-resolved environment inventory from the actual Windows `uv` environment on 2026-09-09.
3. Record exact FFmpeg configure/build/license and codec availability.
4. Record exact Ollama/Qwen/Qwen3-TTS/faster-whisper versions and local model hashes where feasible.
5. Compare actual installed dependency graph to this provisional inventory; unexpected packages are findings, not silently accepted.
