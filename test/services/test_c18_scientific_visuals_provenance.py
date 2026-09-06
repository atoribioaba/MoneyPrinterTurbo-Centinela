from __future__ import annotations

from dataclasses import replace

from app.services.centinela.generative import (
    GeneratedMediaType,
    GeneratedVisualAsset,
    GenerationQuality,
    ScientificVisualStatus,
    VisualGenerationMode,
    VisualGenerationRequest,
)
from app.services.centinela.generative.provenance import (
    build_generated_visual_provenance,
    compute_visual_request_fingerprint,
)


def _request(**overrides) -> VisualGenerationRequest:
    values = {
        "scene_id": "scene-c18",
        "mode": VisualGenerationMode.IMAGE_TO_VIDEO,
        "prompt": "Subtle lunar parallax with stable geometry",
        "quality": GenerationQuality.STANDARD,
        "aspect_ratio": "9:16",
        "source_image": r"D:\ASTRONOMÍA\master-moon.png",
        "negative_prompt": "warped terminator, invented craters",
        "seed": 42,
        "duration_seconds": 4.0,
        "target_width": 1080,
        "target_height": 1920,
    }
    values.update(overrides)
    return VisualGenerationRequest(**values)


def _asset(**overrides) -> GeneratedVisualAsset:
    values = {
        "asset_id": "asset-c18-v1",
        "scene_id": "scene-c18",
        "provider_id": "ltx_local",
        "model_id": "ltx-test-model",
        "media_type": GeneratedMediaType.VIDEO,
        "local_path": r"E:\MPT\tasks\scene-c18.mp4",
        "sha256": "a" * 64,
        "width": 1080,
        "height": 1920,
        "duration_seconds": 4.0,
        "seed": 42,
        "scientific_status": ScientificVisualStatus.RECREACION_VISUAL,
    }
    values.update(overrides)
    return GeneratedVisualAsset(**values)


def _fingerprint(request: VisualGenerationRequest, source_hash: str = "b" * 64) -> str:
    fingerprint, complete = compute_visual_request_fingerprint(
        request,
        source_image_sha256=source_hash,
    )
    assert complete is True
    return fingerprint


def test_c18_fingerprint_is_deterministic_and_normalizes_numeric_duration():
    first = _request(duration_seconds=4)
    second = _request(duration_seconds=4.0)

    assert _fingerprint(first) == _fingerprint(second)


def test_c18_fingerprint_is_path_free_when_source_bytes_are_identical():
    first = _request(source_image=r"D:\ASTRONOMÍA\master-moon.png")
    second = _request(source_image=r"C:\Other\private\master-moon.png")

    assert _fingerprint(first) == _fingerprint(second)


def test_c18_relevant_request_mutations_change_the_fingerprint():
    baseline = _request()
    baseline_hash = _fingerprint(baseline)

    mutations = (
        replace(baseline, prompt="Different lunar prompt"),
        replace(baseline, negative_prompt="different exclusions"),
        replace(baseline, seed=43),
        replace(baseline, quality=GenerationQuality.PREVIEW),
        replace(baseline, aspect_ratio="16:9"),
        replace(baseline, duration_seconds=5.0),
        replace(baseline, target_width=720, target_height=1280),
    )

    assert all(_fingerprint(mutated) != baseline_hash for mutated in mutations)
    different_source, complete = compute_visual_request_fingerprint(
        baseline,
        source_image_sha256="c" * 64,
    )
    assert complete is True
    assert different_source != baseline_hash


def test_c18_i2v_identity_is_explicitly_incomplete_without_source_hash():
    fingerprint, complete = compute_visual_request_fingerprint(_request())

    assert len(fingerprint) == 64
    assert complete is False


def test_c18_non_i2v_identity_does_not_require_a_source_hash():
    request = VisualGenerationRequest(
        scene_id="scene-t2v",
        mode=VisualGenerationMode.TEXT_TO_VIDEO,
        prompt="Cinematic orbital visualization",
        duration_seconds=4,
        seed=7,
    )

    fingerprint, complete = compute_visual_request_fingerprint(request)

    assert len(fingerprint) == 64
    assert complete is True


def test_c18_safe_provenance_binds_request_provider_model_and_asset():
    request = _request()
    asset = _asset()
    record = build_generated_visual_provenance(
        request,
        asset,
        source_image_sha256="b" * 64,
    )

    assert record["source_type"] == "AI_GENERATED"
    assert record["scientific_status"] == "RECREACION_VISUAL"
    assert record["generation_quality"] == "standard"
    assert record["aspect_ratio"] == "9:16"
    assert record["request_identity_complete"] is True
    assert len(str(record["request_sha256"])) == 64
    assert len(str(record["generation_identity_sha256"])) == 64
    assert len(str(record["prompt_sha256"])) == 64
    assert len(str(record["negative_prompt_sha256"])) == 64

    serialized = repr(record)
    assert request.prompt not in serialized
    assert request.negative_prompt not in serialized
    assert request.source_image not in serialized
    assert asset.local_path not in serialized


def test_c18_generation_identity_changes_if_output_or_model_changes():
    request = _request()
    baseline = build_generated_visual_provenance(
        request,
        _asset(),
        source_image_sha256="b" * 64,
    )
    changed_output = build_generated_visual_provenance(
        request,
        _asset(sha256="d" * 64),
        source_image_sha256="b" * 64,
    )
    changed_model = build_generated_visual_provenance(
        request,
        _asset(model_id="other-model"),
        source_image_sha256="b" * 64,
    )

    assert baseline["request_sha256"] == changed_output["request_sha256"]
    assert baseline["request_sha256"] == changed_model["request_sha256"]
    assert baseline["generation_identity_sha256"] != changed_output[
        "generation_identity_sha256"
    ]
    assert baseline["generation_identity_sha256"] != changed_model[
        "generation_identity_sha256"
    ]


def test_c18_provenance_never_promotes_generated_visual_to_verified_fact():
    record = build_generated_visual_provenance(
        _request(),
        _asset(),
        source_image_sha256="b" * 64,
    )

    assert record["scientific_status"] == "RECREACION_VISUAL"
    assert record["scientific_status"] != "HECHO_VERIFICADO"
