from app.models.delivery_render import DeliveryRenderRequest, FFmpegCapabilityHint, DeliveryRenderStatus
from app.models.quality_gates import QualityGatesPlan
from app.services.delivery_render import build_delivery_render


def fixture(ready=False, nvenc=True):
    gates = QualityGatesPlan.model_construct(
        subject="Fixture",
        source_plan_context_hash="ctx",
        technical_ready=ready,
        quality_gates_hash="g",
    )
    ffmpeg = FFmpegCapabilityHint(
        ffmpeg_present=True,
        ffmpeg_version="fixture",
        h264_nvenc_listed=nvenc,
        libx264_listed=True,
        nvenc_social_probe_success=nvenc,
        nvenc_master_probe_success=nvenc,
        capability_probe_invocations=2 if nvenc else 0,
    )
    return DeliveryRenderRequest.model_construct(quality_gates=gates, ffmpeg=ffmpeg)


def test_current_blocked_quality_gate_blocks_render():
    result = build_delivery_render(fixture(False, True))
    assert result.status == DeliveryRenderStatus.BLOCKED_BY_QUALITY_GATES
    assert result.renders_project_video is False


def test_master_and_social_profiles_are_exact():
    result = build_delivery_render(fixture(False, True))
    dims = {(p.width, p.height, p.fps) for p in result.profiles}
    assert dims == {(2160, 3840, 30), (1080, 1920, 30)}


def test_master_is_not_social_upscale():
    result = build_delivery_render(fixture(False, True))
    assert result.upscales_social_to_master is False
    assert all(p.source_strategy == "ORIGINAL_SOURCE_RERENDER" for p in result.profiles)


def test_nvenc_fallback():
    result = build_delivery_render(fixture(False, False))
    assert all(p.effective_codec_candidate == "libx264" for p in result.profiles)


def test_ready_means_explicit_render_approval_not_auto_render():
    result = build_delivery_render(fixture(True, True))
    assert result.status == DeliveryRenderStatus.READY_FOR_EXPLICIT_RENDER_APPROVAL
    assert result.project_render_invocations == 0
    assert result.human_render_approval_required is True


def test_hash_deterministic():
    assert (
        build_delivery_render(fixture(False, True)).delivery_render_hash
        == build_delivery_render(fixture(False, True)).delivery_render_hash
    )
