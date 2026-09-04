from pathlib import Path

import pytest

from app.services.centinela.generative.contracts import (
    GeneratedMediaType,
    GeneratedVisualAsset,
    ScientificVisualStatus,
    VisualGenerationMode,
    VisualGenerationRequest,
)
from app.services.centinela.generative.mpt_bridge import (
    GeneratedMaterialBridgeError,
    generated_video_to_material,
)


def _request(source_image: str) -> VisualGenerationRequest:
    return VisualGenerationRequest(
        scene_id="scene-2",
        mode=VisualGenerationMode.IMAGE_TO_VIDEO,
        prompt="Subtle lunar motion, fixed astronomical geometry",
        source_image=source_image,
        duration_seconds=4.2,
    )


def _asset(path: Path, media_type: GeneratedMediaType) -> GeneratedVisualAsset:
    return GeneratedVisualAsset(
        asset_id="asset-2",
        scene_id="scene-2",
        provider_id="ltx_local",
        model_id="ltx-test",
        media_type=media_type,
        local_path=str(path),
        sha256="b" * 64,
        width=512,
        height=768,
        duration_seconds=4.2 if media_type is GeneratedMediaType.VIDEO else None,
        scientific_status=ScientificVisualStatus.RECREACION_VISUAL,
    )


def test_generated_video_becomes_mpt_material_with_safe_provenance(
    tmp_path: Path,
) -> None:
    source_image = tmp_path / "moon.png"
    source_image.write_bytes(b"image")
    video = tmp_path / "scene-2.mp4"
    video.write_bytes(b"video")
    request = _request(str(source_image))

    material = generated_video_to_material(
        request,
        _asset(video, GeneratedMediaType.VIDEO),
        source_image_sha256="c" * 64,
    )

    assert material.provider == "ltx_local"
    assert material.url == str(video.resolve())
    assert material.duration == 5
    assert material.source_info is not None
    assert material.source_info["source_type"] == "AI_GENERATED"
    assert material.source_info["generation_mode"] == "image_to_video"
    assert material.source_info["scientific_status"] == "RECREACION_VISUAL"
    assert material.source_info["generation_quality"] == "standard"
    assert material.source_info["source_image_sha256"] == "c" * 64
    assert "prompt" not in material.source_info


def test_generated_image_cannot_enter_video_composer(tmp_path: Path) -> None:
    image = tmp_path / "generated.png"
    image.write_bytes(b"image")
    request = VisualGenerationRequest(
        scene_id="scene-2",
        mode=VisualGenerationMode.TEXT_TO_IMAGE,
        prompt="Moon over a Castilian horizon",
    )

    with pytest.raises(GeneratedMaterialBridgeError, match="only generated video"):
        generated_video_to_material(
            request,
            _asset(image, GeneratedMediaType.IMAGE),
        )


def test_missing_generated_video_fails_closed(tmp_path: Path) -> None:
    request = _request(str(tmp_path / "moon.png"))
    missing = tmp_path / "missing.mp4"

    with pytest.raises(GeneratedMaterialBridgeError, match="does not exist"):
        generated_video_to_material(
            request,
            _asset(missing, GeneratedMediaType.VIDEO),
        )
