from app.services.centinela.generative import (
    GeneratedMediaType,
    GeneratedVisualAsset,
    VisualGenerationMode,
    VisualGenerationRequest,
)
from app.services.centinela.generative.provenance import (
    build_generated_visual_provenance,
)


def test_ai_provenance_hashes_prompt_and_hides_absolute_paths() -> None:
    prompt = "Cinematic Moonrise over a stable real-world horizon"
    request = VisualGenerationRequest(
        scene_id="scene-007",
        mode=VisualGenerationMode.IMAGE_TO_VIDEO,
        prompt=prompt,
        source_image=r"D:\ASTRONOMIA\master.png",
        seed=42,
        duration_seconds=4,
    )
    asset = GeneratedVisualAsset(
        asset_id="asset-007-v1",
        scene_id="scene-007",
        provider_id="ltx_local",
        model_id="ltxv-2b-0.9.8-distilled",
        media_type=GeneratedMediaType.VIDEO,
        local_path=r"E:\MPT\tasks\scene-007.mp4",
        sha256="c" * 64,
        width=512,
        height=768,
        duration_seconds=4,
        seed=42,
    )

    record = build_generated_visual_provenance(
        request,
        asset,
        source_image_sha256="d" * 64,
    )

    assert record["source_type"] == "AI_GENERATED"
    assert record["generation_mode"] == "image_to_video"
    assert record["scientific_status"] == "RECREACION_VISUAL"
    assert record["local_file"] == "scene-007.mp4"
    assert record["source_image_sha256"] == "d" * 64
    assert record["prompt_sha256"] != prompt
    assert prompt not in str(record)
    assert "E:\\MPT" not in str(record)
    assert "D:\\ASTRONOMIA" not in str(record)
