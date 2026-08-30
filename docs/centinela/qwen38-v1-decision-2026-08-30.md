# Qwen3.8 decision record for Centinela V1

Date: 2026-08-30
Scope: model-selection decision only. No model download is authorized by this document.

## Status

- `QWEN38_EXISTS=VERIFIED`
- `QWEN38_27B_RELEASE_DATE=2026-08-14`
- `QWEN38_27B_LICENSE=APACHE-2.0`
- `QWEN38_LOCAL_AB_TEST=DEFERRED`
- `QWEN38_DOWNLOAD_AUTHORIZED=FALSE`
- `V1_LOCAL_LLM_BASELINE=QWEN3.5_4B_Q4_K_M`
- `PC_REVALIDATION_REQUIRED=TRUE`

## Primary-source facts

The official Qwen repository records Qwen3.8-27B as released on 2026-08-14. The official Qwen3.8-27B Hugging Face model repository identifies the model license as Apache-2.0.

Qwen3.8-27B is a 27B-class model and is multimodal in its official model card. That makes it materially larger than the current 4B-class local baseline.

## Hardware fit

Target workstation:

- RTX 2060 6 GB VRAM
- Ryzen 7 3700X
- 16 GB system RAM
- Windows 11 Pro

A 27B-class model is not a sensible V1 default for this hardware when the project priorities are compatibility, stability, quality, cost zero, performance and avoiding OOM/swapping. Prior project audit estimated common local quantized footprints well beyond the 6 GB VRAM budget; that estimate is retained as prior evidence and must not be treated as a fresh local benchmark.

## Current selected baseline

Prior local evidence before the no-PC period:

- model: `qwen3.5:4b-q4_K_M`
- runtime: Ollama loopback
- context: 8192 in the tested configuration
- prior GPU evidence: model fitted on RTX 2060 with near-full VRAM use

These are `PRIOR_LOCAL_EVIDENCE`, not a cloud re-certification. They must be rechecked after 2026-09-09.

## Decision

| Candidate | V1 decision | Rationale |
|---|---|---|
| Qwen3.5 4B Q4_K_M | MANTENER | already proven locally enough to remain the stable V1 baseline pending revalidation |
| Qwen3.8 27B | PRUEBA A/B DIFERIDA | potentially higher quality but disproportionate memory/runtime footprint for 6 GB VRAM + 16 GB RAM |
| Remote/API Qwen3.8 | NO FIJAR COMO V1 LOCAL | changes cost/privacy/offline assumptions and API access is not assumed free |

## Re-open criteria

Qwen3.8 local evaluation may be reopened only if one of these becomes true:

1. a substantially smaller official Qwen3.8 model is released with a realistic 6 GB VRAM / 16 GB RAM profile;
2. a verified quantization/runtime demonstrates acceptable quality, RAM/VRAM and latency on this exact workstation;
3. V1 is already frozen and the test is isolated as a post-V1 A/B experiment.

## Required PC evidence if reopened

- exact model and quantization;
- model/license source;
- disk size;
- load success;
- GPU/CPU split;
- VRAM peak;
- RAM peak;
- tokens/s or end-to-end task time;
- Spanish scientific-writing quality;
- FactLock compliance;
- OOM/swap behavior;
- comparison against the 4B baseline.

Until then, no multi-GB Qwen3.8 download is justified.
