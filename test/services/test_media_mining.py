from app.models.astromedia import MediaType
from app.models.media_mining import MediaMiningRequest, MediaMiningStatus
from app.models.shot_quality import ShotQualityPlan, ShotQualitySceneScore, ShotQualityStatus
from app.services.media_mining import build_media_mining


def fixture(status=ShotQualityStatus.NOT_SCORABLE, placeholder=True, media_type=None, path=None):
    scene = ShotQualitySceneScore.model_construct(
        scene_number=1,
        source_path=path,
        media_type=media_type,
        placeholder=placeholder,
        status=status,
    )
    quality = ShotQualityPlan.model_construct(
        subject="Fixture",
        source_plan_context_hash="ctx",
        scene_count=1,
        scenes=[scene],
        quality_hash="q",
    )
    return MediaMiningRequest.model_construct(shot_quality=quality)


def test_placeholder_is_noop():
    result = build_media_mining(fixture())
    assert result.placeholder_count == 1
    assert result.scenes[0].status == MediaMiningStatus.PLACEHOLDER_NOT_APPLICABLE


def test_image_is_single_shot():
    result = build_media_mining(
        fixture(
            status=ShotQualityStatus.SCORED,
            placeholder=False,
            media_type=MediaType.IMAGE,
            path="image.jpg",
        )
    )
    assert result.image_single_shot_count == 1


def test_video_requires_detection_but_does_not_run_it():
    result = build_media_mining(
        fixture(
            status=ShotQualityStatus.SCORED,
            placeholder=False,
            media_type=MediaType.VIDEO,
            path="video.mp4",
        )
    )
    item = result.scenes[0]
    assert item.status == MediaMiningStatus.VIDEO_DETECTION_REQUIRED
    assert item.detector == "AdaptiveDetector"
    assert item.execution_ready is False
    assert result.scenedetect_invocations == 0


def test_hash_is_deterministic():
    assert (
        build_media_mining(fixture()).media_mining_hash
        == build_media_mining(fixture()).media_mining_hash
    )


def test_guardrails():
    result = build_media_mining(fixture())
    assert result.analyzes_video is False
    assert result.splits_video is False
    assert result.downloads_dependencies is False
    assert result.modifies_sources is False
