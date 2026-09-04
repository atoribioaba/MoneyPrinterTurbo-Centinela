"""Safe provenance records for AI-generated scene assets."""

import hashlib
import re

from app.services.centinela.generative.contracts import (
    GeneratedVisualAsset,
    VisualGenerationRequest,
)
from app.services.centinela.provenance import sanitize_provenance


_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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

    source_image_hash = str(source_image_sha256 or "").strip()
    if source_image_hash and not _SHA256_PATTERN.fullmatch(source_image_hash):
        raise ValueError("source_image_sha256 must be a valid SHA-256 digest")

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
            "model": asset.model_id[:512],
            "scientific_status": asset.scientific_status.value,
            "prompt_sha256": _sha256_text(request.prompt),
            "local_inference": bool(local_inference),
        }
    )

    if request.seed is not None:
        record["seed"] = request.seed
    if source_image_hash:
        record["source_image_sha256"] = source_image_hash.lower()

    return record
