from datetime import datetime, timezone

from app.models.delivery_render import DeliveryProfile, DeliveryRenderPlan, DeliveryRenderStatus
from app.models.production_orchestrator import ProductionOrchestratorRequest, ProductionOrchestratorStatus
from app.models.quality_gates import QualityGateCheck, QualityGatesPlan, QualityGateStatus
from app.services.production_orchestrator import build_production_orchestrator

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def gates(ready=True):
    checks=[QualityGateCheck(check_id="x", passed=ready, detail="x")]
    return QualityGatesPlan(
        subject="Luna", source_plan_context_hash="ctx", source_comparator_hash="c",
        source_sound_design_hash="s", source_voice_studio_hash="v", source_audio_mastering_hash="a",
        source_subtitles_hash="sub", status=QualityGateStatus.READY_FOR_HUMAN_REVIEW if ready else QualityGateStatus.BLOCKED,
        check_count=1, passed_count=1 if ready else 0, failed_count=0 if ready else 1,
        technical_ready=ready, publication_eligible_after_human_approval=ready, checks=checks,
        quality_gates_hash="q", generated_at_utc=NOW,
    )


def delivery(ready=True):
    return DeliveryRenderPlan(
        subject="Luna", source_plan_context_hash="ctx", source_quality_gates_hash="q",
        status=DeliveryRenderStatus.READY_FOR_EXPLICIT_RENDER_APPROVAL if ready else DeliveryRenderStatus.BLOCKED_BY_QUALITY_GATES,
        ffmpeg_present=True, h264_nvenc_listed=True, libx264_listed=True, capability_probe_invocations=2,
        profile_count=1, profiles=[DeliveryProfile(profile_id="SOCIAL", width=1080, height=1920, fps=30, requested_codec="h264_nvenc", effective_codec_candidate="h264_nvenc")],
        delivery_render_hash="d", generated_at_utc=NOW,
    )


def test_ready_for_existing_video_base_when_gates_pass():
    result=build_production_orchestrator(ProductionOrchestratorRequest(quality_gates=gates(), delivery=delivery()))
    assert result.status == ProductionOrchestratorStatus.READY_FOR_VIDEO_BASE
    assert result.next_action == "RUN_EXISTING_F6_VIDEO_BASE_RENDER"
    assert result.invokes_render is False


def test_blocked_reuses_existing_gates():
    result=build_production_orchestrator(ProductionOrchestratorRequest(quality_gates=gates(False), delivery=delivery(False)))
    assert result.status == ProductionOrchestratorStatus.BLOCKED_BY_QUALITY_OR_DELIVERY
    assert result.auto_publication is False
