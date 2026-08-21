from app.models.selective_upscaling import (
    SelectiveUpscalingRequest,
    UpscaleSceneStatus,
)
from app.models.shot_quality import (
    ShotQualityBand,
    ShotQualityPlan,
    ShotQualitySceneScore,
    ShotQualityStatus,
)
from app.models.video_base import VideoBasePlan, VideoBaseScenePlan
from app.services.selective_upscaling import build_selective_upscaling


def fixture(placeholder=True, width=0, height=0, quality_status=ShotQualityStatus.NOT_SCORABLE):
    video_scene = VideoBaseScenePlan.model_construct(
        scene_number=1,
        placeholder=placeholder,
        source_width=width,
        source_height=height,
    )
    video = VideoBasePlan.model_construct(
        subject="Fixture",
        source_plan_context_hash="ctx",
        version="video-base-v0.1",
        output_width=1080,
        output_height=1920,
        scene_count=1,
        scenes=[video_scene],
    )
    quality_scene = ShotQualitySceneScore.model_construct(
        scene_number=1,
        status=quality_status,
        band=(
            ShotQualityBand.NOT_SCORABLE
            if quality_status == ShotQualityStatus.NOT_SCORABLE
            else ShotQualityBand.ANALYSIS_FAILED
        ),
    )
    quality = ShotQualityPlan.model_construct(
        source_plan_context_hash="ctx",
        scene_count=1,
        scenes=[quality_scene],
        quality_hash="q",
    )
    return SelectiveUpscalingRequest.model_construct(
        video_base=video,
        shot_quality=quality,
    )


def test_placeholder_is_noop():
    result = build_selective_upscaling(fixture())
    assert result.placeholder_count == 1
    assert result.scenes[0].status == UpscaleSceneStatus.PLACEHOLDER_NOT_APPLICABLE


def test_full_resolution_source_does_not_need_upscale():
    request = fixture(
        placeholder=False,
        width=2160,
        height=3840,
        quality_status=ShotQualityStatus.ANALYSIS_FAILED,
    )
    result = build_selective_upscaling(request)
    assert result.scenes[0].status == UpscaleSceneStatus.NOT_REQUIRED


def test_lower_resolution_requires_ab_review_not_auto_run():
    request = fixture(
        placeholder=False,
        width=720,
        height=1280,
        quality_status=ShotQualityStatus.ANALYSIS_FAILED,
    )
    result = build_selective_upscaling(request)
    item = result.scenes[0]
    assert item.status == UpscaleSceneStatus.A_B_REVIEW_REQUIRED
    assert item.execution_ready is False
    assert item.astronomy_fidelity_review_required is True


def test_hash_is_deterministic():
    assert (
        build_selective_upscaling(fixture()).selective_upscaling_hash
        == build_selective_upscaling(fixture()).selective_upscaling_hash
    )


def test_guardrails():
    result = build_selective_upscaling(fixture())
    assert result.runs_upscaler is False
    assert result.downloads_models is False
    assert result.renders_video is False
    assert result.invents_astronomy_detail is False
