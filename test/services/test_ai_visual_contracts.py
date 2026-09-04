import pytest

from app.services.centinela.generative import (
    GeneratedMediaType,
    GeneratedVisualAsset,
    GenerationQuality,
    LowVramFallbackPolicy,
    SceneAssetIndex,
    ScientificVisualStatus,
    VisualGenerationMode,
    VisualGenerationRequest,
)


def _video_asset(asset_id: str, scene_id: str = "scene-001") -> GeneratedVisualAsset:
    return GeneratedVisualAsset(
        asset_id=asset_id,
        scene_id=scene_id,
        provider_id="ltx_local",
        model_id="ltxv-2b-0.9.8-distilled",
        media_type=GeneratedMediaType.VIDEO,
        local_path=f"C:/tasks/{asset_id}.mp4",
        sha256="a" * 64,
        width=512,
        height=768,
        duration_seconds=4.0,
    )


def test_image_to_video_requires_source_image() -> None:
    with pytest.raises(ValueError, match="requires source_image"):
        VisualGenerationRequest(
            scene_id="scene-001",
            mode=VisualGenerationMode.IMAGE_TO_VIDEO,
            prompt="Slow cinematic push toward the Moon",
            duration_seconds=4,
        )


def test_generated_asset_cannot_self_certify_science() -> None:
    with pytest.raises(ValueError, match="cannot self-certify"):
        GeneratedVisualAsset(
            asset_id="asset-001",
            scene_id="scene-001",
            provider_id="zimage_local",
            model_id="Z-Image-Turbo",
            media_type=GeneratedMediaType.IMAGE,
            local_path="C:/tasks/asset-001.png",
            sha256="b" * 64,
            width=768,
            height=1024,
            scientific_status=ScientificVisualStatus.HECHO_VERIFICADO,
        )


def test_scene_asset_index_preserves_versions_and_latest() -> None:
    index = SceneAssetIndex()
    first = _video_asset("asset-v1")
    second = _video_asset("asset-v2")

    index.register(first)
    index.register(second)

    assert index.for_scene("scene-001") == (first, second)
    assert index.latest("scene-001") == second


def test_low_vram_policy_allows_only_bounded_quality_downgrade() -> None:
    policy = LowVramFallbackPolicy(max_retries=1)

    assert policy.next_quality(
        GenerationQuality.MASTER,
        retries_used=0,
    ) is GenerationQuality.STANDARD
    assert policy.next_quality(
        GenerationQuality.STANDARD,
        retries_used=1,
    ) is None
