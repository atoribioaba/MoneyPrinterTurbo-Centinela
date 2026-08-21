from app.models.media_mining import MediaMiningPlan, MediaMiningScene, MediaMiningStatus
from app.models.quality_comparator import QualityComparatorRequest, QualityComparisonStatus
from app.models.selective_upscaling import SelectiveUpscalingPlan, UpscaleScene, UpscaleSceneStatus
from app.models.shot_quality import ShotQualityPlan, ShotQualitySceneScore, ShotQualityStatus
from app.services.quality_comparator import build_quality_comparator


def fixture(placeholder=True, quality_status=ShotQualityStatus.NOT_SCORABLE, upscale_status=UpscaleSceneStatus.PLACEHOLDER_NOT_APPLICABLE):
    qscene = ShotQualitySceneScore.model_construct(
        scene_number=1,
        placeholder=placeholder,
        status=quality_status,
        score=None if placeholder else 0.8,
    )
    quality = ShotQualityPlan.model_construct(
        subject="Fixture",
        source_plan_context_hash="ctx",
        scene_count=1,
        scenes=[qscene],
        quality_hash="q",
    )
    upscene = UpscaleScene.model_construct(
        scene_number=1,
        status=upscale_status,
        candidate_engine=(
            "Real-ESRGAN-ncnn-vulkan"
            if upscale_status == UpscaleSceneStatus.A_B_REVIEW_REQUIRED
            else None
        ),
    )
    upscaling = SelectiveUpscalingPlan.model_construct(
        subject="Fixture",
        source_plan_context_hash="ctx",
        scene_count=1,
        scenes=[upscene],
        selective_upscaling_hash="u",
    )
    mscene = MediaMiningScene.model_construct(
        scene_number=1,
        status=MediaMiningStatus.PLACEHOLDER_NOT_APPLICABLE if placeholder else MediaMiningStatus.IMAGE_SINGLE_SHOT,
    )
    mining = MediaMiningPlan.model_construct(
        subject="Fixture",
        source_plan_context_hash="ctx",
        scene_count=1,
        scenes=[mscene],
        media_mining_hash="m",
    )
    return QualityComparatorRequest.model_construct(
        shot_quality=quality,
        upscaling=upscaling,
        media_mining=mining,
    )


def test_placeholder_not_comparable():
    result = build_quality_comparator(fixture())
    assert result.placeholder_count == 1


def test_baseline_accepted_without_upscale_candidate():
    result = build_quality_comparator(
        fixture(
            placeholder=False,
            quality_status=ShotQualityStatus.SCORED,
            upscale_status=UpscaleSceneStatus.NOT_REQUIRED,
        )
    )
    assert result.scenes[0].status == QualityComparisonStatus.BASELINE_ACCEPTED


def test_upscale_never_wins_without_ab():
    result = build_quality_comparator(
        fixture(
            placeholder=False,
            quality_status=ShotQualityStatus.SCORED,
            upscale_status=UpscaleSceneStatus.A_B_REVIEW_REQUIRED,
        )
    )
    item = result.scenes[0]
    assert item.status == QualityComparisonStatus.A_B_COMPARISON_REQUIRED
    assert item.winner is None
    assert item.human_review_required is True


def test_hash_deterministic():
    assert (
        build_quality_comparator(fixture()).quality_comparator_hash
        == build_quality_comparator(fixture()).quality_comparator_hash
    )


def test_guardrails():
    result = build_quality_comparator(fixture())
    assert result.executes_ab_comparison is False
    assert result.selects_winner is False
    assert result.analyzes_new_frames is False
