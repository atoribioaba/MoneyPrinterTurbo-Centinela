"""Bridge approved generated video assets into MPT's existing material input."""

import math
import os

from app.models.schema import MaterialInfo
from app.services.centinela.generative.contracts import (
    GeneratedMediaType,
    GeneratedVisualAsset,
    VisualGenerationRequest,
)
from app.services.centinela.generative.provenance import (
    build_generated_visual_provenance,
)


class GeneratedMaterialBridgeError(ValueError):
    """Raised when a generated asset cannot safely enter the MPT composer."""


def generated_video_to_material(
    request: VisualGenerationRequest,
    asset: GeneratedVisualAsset,
    *,
    source_image_sha256: str | None = None,
    require_existing_file: bool = True,
) -> MaterialInfo:
    """Convert one generated video into the legacy MPT MaterialInfo contract.

    Images are deliberately rejected: the current composer consumes video paths,
    so a generated master image must first pass through I2V or another explicit
    image-to-video stage. This keeps the bridge narrow and fail-closed.
    """

    if request.scene_id != asset.scene_id:
        raise GeneratedMaterialBridgeError(
            "request and generated asset must belong to the same scene"
        )
    if asset.media_type is not GeneratedMediaType.VIDEO:
        raise GeneratedMaterialBridgeError(
            "only generated video assets can enter the MPT video composer"
        )

    local_path = os.path.realpath(asset.local_path)
    if require_existing_file and not os.path.isfile(local_path):
        raise GeneratedMaterialBridgeError(
            "generated video file does not exist"
        )

    provenance = build_generated_visual_provenance(
        request,
        asset,
        source_image_sha256=source_image_sha256,
        local_inference=True,
    )
    provenance["generation_quality"] = request.quality.value

    return MaterialInfo(
        provider=asset.provider_id,
        url=local_path,
        duration=max(1, math.ceil(float(asset.duration_seconds or 0.0))),
        source_info=provenance,
    )
