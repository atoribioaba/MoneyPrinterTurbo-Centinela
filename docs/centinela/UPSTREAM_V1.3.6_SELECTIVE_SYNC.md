# EL CENTINELA DEL UNIVERSO — MoneyPrinterTurbo v1.3.6 selective-sync audit

Date: 2026-09-06

Upstream: `harry0703/MoneyPrinterTurbo`

Stable upstream reference: `v1.3.6` (`cbbb366393105d5cefc254dc9ed492d43da0711b`)

Centinela C2 base: `888a11c3e8ed7d4f705e4b3965b906cfad295a10`

Policy: **selective sync, not a bulk merge**. Centinela contains project-specific security, provenance, astronomy-media, UI, provider-registry and control-plane changes that must not be overwritten by an upstream tree replacement.

`app.__version__` remains unchanged until compatibility is intentionally declared. A selective backport is not the same thing as being byte-for-byte MoneyPrinterTurbo v1.3.6.

## Decision vocabulary

- `APLICADO`: upstream behavior was missing and has been backported.
- `YA EQUIVALENTE`: Centinela already had the material behavior.
- `SUSTITUIDO POR CENTINELA`: Centinela has a project-specific implementation that meets or exceeds the upstream capability.
- `PENDIENTE`: useful but deliberately outside this hardening batch.
- `OMITIDO DEL BASELINE`: not suitable for the zero-cost/default Centinela path.
- `NO APLICA AHORA`: depends on an architecture currently deferred.

## v1.3.6 compatibility matrix

| Upstream v1.3.6 item | Centinela status | Decision / evidence |
|---|---|---|
| Same-origin browser API default | Implemented | `APLICADO`. `app/asgi.py` now defaults to same-origin, supports an explicit `CORS_ALLOWED_ORIGINS` allowlist, rejects untrusted browser origins, and does not combine wildcard origin with credentials. |
| Container provenance + SBOM attestations | Docker publishing is not the current canonical deployment | `NO APLICA AHORA`. Docker remains deferred until the Windows-native/PC reconciliation decision is revisited. |
| Real narration duration from written audio | Implemented | `APLICADO`. TTS generation measures the produced audio file and falls back to SubMaker timing only when file measurement is unavailable. |
| SiliconFlow subtitle end anchored to full audio | Implemented | `APLICADO`. Legacy subtitle timing is generated from the measured complete audio duration. |
| Guaranteed `AudioFileClip` cleanup | Implemented where Centinela still needed it | `APLICADO`. ElevenLabs and Chatterbox now close clips in `finally`; other Centinela paths already used safe lifetime handling or different implementations. |
| Non-greedy script bracket/parenthesis cleanup | Implemented | `APLICADO`. Independent bracketed/parenthesized fragments are no longer greedily collapsed into one deletion. |
| Remove final false LLM retry warning | Implemented | `APLICADO`. Retry logging now uses the real remaining-attempt condition. |
| Redis URL without password | Implemented | `APLICADO`. Empty/None password omits the authentication segment instead of producing `redis://:None@...`. |
| Cross-mount logging stability | Implemented | `APLICADO`. Relative-path formatting handles Windows/mapped-drive `relpath` failures and preserves external absolute paths. |
| Windows CLI UTF-8 output | Implemented | `APLICADO`. `cli.py` reconfigures stdout/stderr to UTF-8 with replacement fallback before command execution when invoked as the CLI entrypoint. |
| Download filename quoting / safe filename behavior | Implemented | `APLICADO`. API download uses `FileResponse(filename=...)` and WebUI protects Windows-reserved names. |
| WebUI Windows-reserved names | Implemented | `APLICADO`. `CON`, `PRN`, `AUX`, `NUL`, `COM1..9`, `LPT1..9` and stem variants are prefixed safely. |
| Source clip `cover` / `contain` | Centinela already has `fit` / `cover` plus focal positioning | `SUSTITUIDO POR CENTINELA`. `fit` is the complete-frame/letterbox behavior corresponding to upstream `contain`; `cover` fills/crops and Centinela additionally supports normalized focal coordinates. No upstream replacement is needed. |
| Headless WebUI preview fallback | Desktop Windows is the current target; direct task download already exists | `PENDIENTE`. Useful for future headless/server deployments, not required to close the present Windows-native hardening batch. |
| CLI inherits saved WebUI defaults | Current CLI keeps explicit CLI/model defaults | `PENDIENTE`. Valuable for automation, but behavior-changing; should be introduced with dedicated precedence tests rather than folded into a security sync. |
| CLI batch manifest mode | Not part of the current certified CLI contract | `PENDIENTE`. Candidate for a dedicated automation batch after C3. |
| French and Korean WebUI translations | Not present in the current Centinela locale set | `PENDIENTE`. Low priority for the Spanish-first Centinela deployment; should not block runtime hardening. |
| OpenRouter / APIMart LLM provider entries | Not required by zero-cost/local baseline | `OMITIDO DEL BASELINE`. Existing provider registry already supports local Ollama and multiple compatible gateways. Add only if an explicit use case justifies credentials/cost. |
| Native VolcEngine Seedance video generation | Cloud/paid generative path | `OMITIDO DEL BASELINE`. Centinela's AI Visual workstream is intentionally a separate pre-composition layer and must remain provider-agnostic. |
| OFox multi-model video generation | Cloud aggregation path | `OMITIDO DEL BASELINE`. Not canonical for the zero-cost/local-first architecture. |
| Metaso MiniMax H3 video generation | Cloud/paid generative path | `OMITIDO DEL BASELINE`. May be A/B tested later as an optional provider, never required by the baseline. |
| OpenAI-compatible text-to-image material source | Upstream cloud/gateway implementation not imported | `PENDIENTE / SUSTITUIDO ARCHITECTURALLY`. Generative image/video material belongs to Centinela AI Visual before final MPT composition; evaluate local/OSS and optional cloud adapters there rather than coupling it to the stock-material path. |
| Upload-Post Auto-Publish settings | Legacy Upload-Post integration exists | `SUSTITUIDO POR C2`. Direct official YouTube/TikTok/Instagram adapters are the canonical path. Upload-Post is to remain only an optional fallback; automatic publication is forbidden by Centinela policy. |
| Decouple Upload-Post configuration from auto-publish | Configuration and enablement are already distinct | `YA EQUIVALENTE`, with a further Centinela requirement: `AUTO_PUBLICATION=FALSE` and human approval remains mandatory. |
| Reorganized/grouped video providers | Centinela has a capability-based provider registry | `SUSTITUIDO POR CENTINELA`. Provider selection is classified by kind/capability rather than copied from upstream UI grouping. |
| Harden malformed OpenAI-compatible generated-image responses | Upstream image-source implementation is not canonical here | `PENDIENTE` in AI Visual. When an OpenAI-compatible image adapter is admitted, malformed-success responses and local-storage failures must be fail-safe before any paid retry loop. |

## Centinela additions that must not be overwritten by upstream sync

The following are project-specific and take precedence over a bulk upstream merge:

- C1 unified control plane and PC-return fail-closed checks.
- Official direct social publication adapters with explicit human approval.
- `AUTO_PUBLICATION=FALSE` invariant.
- NASA and Wikimedia provenance/licensing policies.
- Material provenance persistence and secret-safe URL handling.
- Local material support and astronomy-oriented provider capabilities.
- LiteLLM optionalization rather than baseline dependency.
- TTS/subtitle policy that does not silently download Whisper after an Edge failure.
- FFmpeg/NVENC capability probing and safe fallbacks.
- `fit`/`cover` framing with focal coordinates.
- Centinela-specific WebUI task/history, security and local-runtime hardening.

## Upstream main after v1.3.6

Upstream `main` was inspected separately and is ahead of `v1.3.6`. Post-release changes are **not** automatically accepted into this batch. In particular, newly merged providers/features such as Claude Code require their own compatibility, cost, licensing and architecture review before adoption.

## Exit criteria for C3

C3 can be called cloud-safe only when all of the following are true:

1. C2 final is an ancestor of the C3 head.
2. No temporary workflow with `contents: write` remains in the final tree.
3. Full Python 3.11 and Python 3.13 tests pass.
4. Windows smoke and PC-return PowerShell checks pass.
5. Secret regression scan passes.
6. Selective-sync regressions pass.
7. No live publishing, paid-provider call or physical-PC/GPU result is claimed without evidence.
8. The PR remains DRAFT until explicit human approval.
