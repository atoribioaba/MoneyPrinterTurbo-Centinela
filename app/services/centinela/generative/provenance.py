"""Safe provenance records for AI-generated scene assets."""

import hashlib
import json
import re

from app.services.centinela.generative.contracts import (
    GeneratedVisualAsset,
    VisualGenerationRequest,
)
from app.services.centinela.provenance import sanitize_provenance


_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validated_source_hash(value: str | None) -> str:
    normalized = str(value or "").strip()
    if normalized and not _SHA256_PATTERN.fullmatch(normalized):
        raise ValueError("source_image_sha256 must be a valid SHA-256 digest")
    return normalized.lower()


def _canonical_json_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(canonical)


def compute_visual_request_fingerprint(
    request: VisualGenerationRequest,
    *,
    source_image_sha256: str | None = None,
) -> tuple[str, bool]:
    """Return a path-free canonical fingerprint and identity-completeness flag.

    Raw prompt text, negative-prompt text and local source-image paths never enter
    the canonical payload. Image-to-video identity is complete only when the
    source image is bound by SHA-256.
    """

    if not isinstance(request, VisualGenerationRequest):
        raise TypeError("request must be VisualGenerationRequest")

    source_hash = _validated_source_hash(source_image_sha256)
    source_present = bool(request.source_image)
    identity_complete = not source_present or bool(source_hash)

    payload: dict[str, object] = {
        "scene_id": request.scene_id,
        "generation_mode": request.mode.value,
        "generation_quality": request.quality.value,
        "aspect_ratio": request.aspect_ratio,
        "prompt_sha256": _sha256_text(request.prompt),
        "negative_prompt_sha256": _sha256_text(request.negative_prompt),
        "seed": request.seed,
        "duration_seconds": (
            None
            if request.duration_seconds is None
            else float(request.duration_seconds)
        ),
        "target_width": request.target_width,
        "target_height": request.target_height,
        "source_image_present": source_present,
        "source_image_sha256": source_hash or None,
    }
    return _canonical_json_sha256(payload), identity_complete


def build_generated_visual_provenance(
    request: VisualGenerationRequest,
    asset: GeneratedVisualAsset,
    *,
    source_image_sha256: str | None = None,
    local_inference: bool = True,
) -> dict[str, object]:
    """Build a whitelisted AI provenance record without storing raw prompts.

    The record keeps hashes and reproducibility metadata while avoiding absolute
    local paths and arbitrary prompt text in publication artifacts.
    """

    if request.scene_id != asset.scene_id:
        raise ValueError("request and asset must belong to the same scene")

    source_image_hash = _validated_source_hash(source_image_sha256)
    request_sha256, request_identity_complete = compute_visual_request_fingerprint(
        request,
        source_image_sha256=source_image_hash or None,
    )
    prompt_sha256 = _sha256_text(request.prompt)
    negative_prompt_sha256 = _sha256_text(request.negative_prompt)
    model = asset.model_id[:512]

    record = sanitize_provenance(
        {
            "asset_id": asset.asset_id,
            "sha256": asset.sha256,
            "rendition": {
                "width": asset.width,
                "height": asset.height,
            },
        },
        provider=asset.provider_id,
        local_path=asset.local_path,
        duration=asset.duration_seconds,
    )
    record.update(
        {
            "source_type": "AI_GENERATED",
            "scene_id": asset.scene_id,
            "generation_mode": request.mode.value,
            "generation_quality": request.quality.value,
            "aspect_ratio": request.aspect_ratio,
            "model": model,
            "scientific_status": asset.scientific_status.value,
            "prompt_sha256": prompt_sha256,
            "request_sha256": request_sha256,
            "request_identity_complete": request_identity_complete,
            "local_inference": bool(local_inference),
        }
    )

    if request.negative_prompt:
        record["negative_prompt_sha256"] = negative_prompt_sha256
    if request.seed is not None:
        record["seed"] = request.seed
    if source_image_hash:
        record["source_image_sha256"] = source_image_hash

    record["generation_identity_sha256"] = _canonical_json_sha256(
        {
            "request_sha256": request_sha256,
            "provider": asset.provider_id,
            "model": model,
            "asset_sha256": asset.sha256,
        }
    )

    return record
