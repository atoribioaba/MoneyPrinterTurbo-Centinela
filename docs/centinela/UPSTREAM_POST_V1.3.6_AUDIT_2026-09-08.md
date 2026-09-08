# Upstream post-v1.3.6 audit — 2026-09-08

Repository audited: `harry0703/MoneyPrinterTurbo`

Centinela baseline for this audit:

- current operational branch: `centinela-engineering/c05-c20-windows-path-contract-adversarial-v0.1`
- current operational HEAD: `2c6267c8d9ad3d144ebe6db73189a34c63656ce0`
- selectively synchronized upstream release: `v1.3.6`
- upstream `v1.3.6` commit: `cbbb366393105d5cefc254dc9ed492d43da0711b`

Permanent Centinela invariants remain unchanged:

- `GENERAR → REVISAR → APROBAR → PUBLICAR`
- `AUTO_PUBLICATION=FALSE`
- no merge/freeze/publication is authorized by this audit
- no physical-PC claim is made from cloud inspection

## Executive result

As inspected on 2026-09-08, upstream `main` is 22 commits ahead of the `v1.3.6` release commit and there is no newer stable release than `v1.3.6` in the release list inspected for this audit.

The post-release delta contains one small generic TTS robustness fix that directly applies to the current C20 code, one strong new local/OSS TTS candidate worth a physical-PC A/B, and several optional/irrelevant features that should not be imported into Centinela V1 merely because upstream added them.

Do **not** bulk-merge upstream `main`.

## Decision matrix

| Upstream change | Upstream SHA | Centinela relevance | Decision |
|---|---|---:|---|
| Reject non-finite TTS voice rates (`NaN`/`Inf`) | `b463291b465851741893f48d73120b4d4c63f29c` | High, generic robustness | `BACKPORT_RECOMMENDED` |
| Kokoro self-hosted TTS provider | `bd34691afe099524cb4fa543fd49f914c927ec72` | High as zero-cost/local A/B candidate | `PRUEBA_A_B_PC` |
| Kokoro voice/audio hardening | `883ef2f8d43f4126ccbda7d00eb78885a479b1db` | High if Kokoro is evaluated | `PORT_WITH_KOKORO_ONLY` |
| Word-by-word subtitles + pop animation | `50e91230b2641bf7d520b4367034d3da2e15a5e4` | Optional creative feature | `DEFER_V1_PLUS_A_B` |
| Subtitle animation reliability hardening | `ff64bcdf2f987b97b7504c1b68e2b6c48b46ad7b` | Relevant only if animation feature is adopted | `PORT_ONLY_WITH_FEATURE` |
| BGM preset/music preview | `2b878b4f47737814028ddc50cdb9ea49d0c83701`, `9f0b28f8e87db76feee2d49ad3d98a31b43a9532` | Low; Centinela needs verified music licensing | `DO_NOT_BACKPORT_FOR_V1` |
| Claude Code subscription provider | `4f469431ab8a6fdcff6723b4071fc1e9afc586dc` + hardening | Low for local-zero-cost baseline | `NOT_SELECTED` |
| `webui.sh` path-with-spaces fix | `d4f5e969342e3500d8a58beadfee06a90010a3e7` | Linux shell-specific; native Windows is current architecture candidate | `NO_IMMEDIATE_NEED` |
| Shengsuan generated-video workflow | `5ceffd02a267de2ede0bbdb0fab8d7d875ea9842` | Paid/remote generative material path, not V1 baseline | `NOT_SELECTED` |
| Colab notebook fixes | `4a7a224d8c3c020727fe9aa930bacadb8920fc98` | Not relevant to target Windows workstation | `NO_BACKPORT` |

## Finding UPOST-001 — non-finite voice-rate bug exists in C20

### Upstream evidence

Upstream changed:

```python
if rate <= 0:
```

to:

```python
if not math.isfinite(rate) or rate <= 0:
```

and added regression coverage for `float("nan")` and `float("inf")`.

### Current C20 evidence

C20 already imports `math`, but its `convert_rate_to_percent()` still uses only:

```python
if rate <= 0:
    rate = 1.0
```

Therefore a syntactically valid float such as `NaN`/`Inf` is not normalized by the current helper.

### Classification

`CONFIRMED_CLOUD_FIXABLE_DEFECT`

Severity: **low/medium robustness**, not a security-critical or Golden-blocking defect.

### Recommendation

Do not bulk-sync upstream for this fix.

Preferred handling:

1. preserve C20 as the pre-PC checkpoint;
2. during release-candidate reconciliation, port the minimal one-condition change plus regression tests;
3. test the exact TTS helper and existing Edge TTS suite;
4. keep unrelated post-v1.3.6 provider/UI changes out of the causal patch.

A separate post-C20 patch before PC is justified only if there is a clear operational reason; the defect does not invalidate the read-only PC preflight or C20's Windows path certification.

## Finding UPOST-002 — Kokoro is a serious V1/V1+ TTS candidate

Upstream added a self-hosted OpenAI-compatible Kokoro provider with no new Python dependency in MoneyPrinterTurbo itself and later hardened:

- old/new voice-catalog normalization;
- outage-safe voice selection behavior;
- empty/invalid audio detection;
- temporary-file decode validation before replacing existing output;
- Windows-safe close-before-replace semantics;
- unspeakable-text rejection;
- shared OpenAI-compatible TTS transport tests.

Current external model documentation inspected during this audit describes Kokoro-82M as Apache-2.0, approximately 82M parameters, with Spanish support including two male Spanish voices (`em_alex`, `em_santa`) and one female Spanish voice (`ef_dora`).

This does **not** establish Spanish-from-Spain accent/naturalness or Centinela suitability. Those remain human listening tests.

### Centinela decision

Classification candidate:

`OPEN SOURCE + 100 % GRATUITA` for the model/runtime path, subject to final exact runtime/server license verification.

Decision:

`PRUEBA A/B`

Compare on the physical PC against the already planned V1 TTS candidates using the existing ES-ES acceptance rubric:

- naturalness;
- Spanish pronunciation;
- Spain accent suitability;
- male voice suitability;
- astronomy terminology/pronunciation;
- punctuation/prosody;
- long-script stability;
- latency;
- CPU/RAM/VRAM;
- timestamp quality/availability;
- operational stability.

Do not make Kokoro canonical before this real A/B.

## Finding UPOST-003 — word-by-word subtitles are not automatically better for Centinela

Upstream added word-by-word subtitle timing and optional pop/spring animation, then fixed mask/frame animation reliability.

Centinela's current visual identity explicitly avoids gratuitous transitions/effects and prioritizes cinematic, elegant, scientifically serious presentation. Therefore upstream's feature should not be imported simply because it exists.

Decision:

`DEFER_V1_PLUS_A_B`

If evaluated later:

- native TTS timestamps remain preferred over Whisper when available;
- compare sentence/phrase subtitles vs word-by-word on retention and readability;
- pop animation must default OFF;
- astronomy/scientific legibility takes priority over trend-driven styling.

## Finding UPOST-004 — BGM presets do not solve Centinela's music problem

Upstream's BGM preset/preview functionality improves convenience but does not by itself establish that a music asset is licensed for Instagram/TikTok/YouTube publication.

Decision:

`DO_NOT_BACKPORT_FOR_V1`

Centinela must continue to bind music selection to explicit copyright/license evidence. If a track's rights cannot be demonstrated, classify it:

`LICENCIA NO VERIFICADA`

## Finding UPOST-005 — Claude Code provider is not a V1 baseline

Upstream added a provider using a locally installed Claude CLI and subscription authentication, with later environment/tool isolation hardening.

This does not fit Centinela's current baseline priorities of cost 0, local/privacy and reproducible zero-cost operation, and it adds an external subscription/runtime dependency.

Decision:

`NOT_SELECTED`

No action for V1.

## Finding UPOST-006 — paid/remote generated-video providers remain outside baseline

Post-release Shengsuan workflow changes and the v1.3.6 paid/cloud video providers do not supersede Centinela's architecture:

```text
SCRIPT / SCENE
   ↓
OWN MEDIA / VERIFIED ONLINE MEDIA / EXPLICIT AI RECREATION
   ↓
MPT FINAL COMPOSITION
```

AI recreation remains explicit, scientifically labeled, provenance-bound and human-reviewed.

Decision:

`NO_BASELINE_IMPORT`

## Release-watch conclusion

Current stable upstream release observed: `v1.3.6`.

Current post-release `main` delta inspected: 22 commits ahead of `v1.3.6`.

No post-release change discovered in this audit justifies a bulk upstream merge or invalidates the current C20 pre-PC checkpoint.

The only confirmed generic code defect found in C20 from this delta is the non-finite TTS rate handling issue, which is suitable for a minimal isolated backport during RC reconciliation.

## Required next order

```text
PC READ-ONLY PREFLIGHT
→ preserve local state
→ reconcile local ↔ C20
→ create V1 release-candidate lineage
→ minimal UPOST-001 TTS fix
→ local regression
→ TTS A/B including Kokoro if selected for evaluation
→ real Golden
```

## Status

`UPSTREAM_POST_V136_AUDITED=TRUE`

`UPSTREAM_MAIN_AHEAD_BY=22`

`BULK_UPSTREAM_MERGE_RECOMMENDED=FALSE`

`C20_INVALIDATED=FALSE`

`MINIMAL_TTS_BACKPORT_RECOMMENDED=TRUE`

`KOKORO_PC_A_B_RECOMMENDED=TRUE`

`AUTO_PUBLICATION=FALSE`
