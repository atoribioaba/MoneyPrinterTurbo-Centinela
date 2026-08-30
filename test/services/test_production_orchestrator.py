from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.delivery_render import (
    DeliveryProfile,
    DeliveryRenderPlan,
    DeliveryRenderStatus,
)
from app.models.production_orchestrator import (
    HumanReviewState,
    ProductionOrchestratorPlan,
    ProductionOrchestratorRequest,
    ProductionOrchestratorStatus,
)
from app.models.quality_gates import (
    QualityGateCheck,
    QualityGatesPlan,
    QualityGateStatus,
)
from app.models.video_base import VideoBaseRenderManifest, VideoBaseRenderMode
from app.services.production_orchestrator import build_production_orchestrator

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def gates(ready=True):
    checks = [QualityGateCheck(check_id="x", passed=ready, detail="x")]
    return QualityGatesPlan(
        subject="Luna",
        source_plan_context_hash="ctx",
        source_comparator_hash="c",
        source_sound_design_hash="s",
        source_voice_studio_hash="v",
        source_audio_mastering_hash="a",
        source_subtitles_hash="sub",
        status=(
            QualityGateStatus.READY_FOR_HUMAN_REVIEW
            if ready
            else QualityGateStatus.BLOCKED
        ),
        check_count=1,
        passed_count=1 if ready else 0,
        failed_count=0 if ready else 1,
        technical_ready=ready,
        publication_eligible_after_human_approval=ready,
        checks=checks,
        quality_gates_hash="q",
        generated_at_utc=NOW,
    )


def delivery(ready=True):
    return DeliveryRenderPlan(
        subject="Luna",
        source_plan_context_hash="ctx",
        source_quality_gates_hash="q",
        status=(
            DeliveryRenderStatus.READY_FOR_EXPLICIT_RENDER_APPROVAL
            if ready
            else DeliveryRenderStatus.BLOCKED_BY_QUALITY_GATES
        ),
        ffmpeg_present=True,
        h264_nvenc_listed=True,
        libx264_listed=True,
        capability_probe_invocations=2,
        profile_count=1,
        profiles=[
            DeliveryProfile(
                profile_id="SOCIAL",
                width=1080,
                height=1920,
                fps=30,
                requested_codec="h264_nvenc",
                effective_codec_candidate="h264_nvenc",
            )
        ],
        delivery_render_hash="d",
        generated_at_utc=NOW,
    )


def video_manifest():
    return VideoBaseRenderManifest(
        task_id="task",
        render_mode=VideoBaseRenderMode.CLEAN_BASE,
        output_width=1080,
        output_height=1920,
        fps=30,
        requested_codec="libx264",
        effective_codec="libx264",
        codec_fallback=False,
        ffmpeg_binary="ffmpeg",
        nvenc_probe_success=None,
        concat_mode="copy",
        ffmpeg_version="test",
        scene_count=1,
        placeholder_count=0,
        expected_duration_seconds=1.0,
        rendered_duration_seconds=1.0,
        final_video_path="video.mp4",
        final_video_sha256="A" * 64,
        final_video_codec="h264",
        final_pixel_format="yuv420p",
        final_audio_stream_count=0,
        scenes=[],
        generated_at_utc=NOW,
    )


def test_ready_for_existing_video_base_when_gates_pass():
    result = build_production_orchestrator(
        ProductionOrchestratorRequest(quality_gates=gates(), delivery=delivery())
    )
    assert result.status == ProductionOrchestratorStatus.READY_FOR_VIDEO_BASE
    assert result.next_action == "RUN_EXISTING_F6_VIDEO_BASE_RENDER"
    assert result.invokes_render is False


def test_blocked_reuses_existing_gates():
    result = build_production_orchestrator(
        ProductionOrchestratorRequest(
            quality_gates=gates(False),
            delivery=delivery(False),
        )
    )
    assert result.status == ProductionOrchestratorStatus.BLOCKED_BY_QUALITY_OR_DELIVERY
    assert result.auto_publication is False


def test_video_base_present_stops_at_downstream_review_authority():
    result = build_production_orchestrator(
        ProductionOrchestratorRequest(
            quality_gates=gates(),
            delivery=delivery(),
            video_base_manifest=video_manifest(),
        )
    )
    assert result.status == ProductionOrchestratorStatus.WAITING_FOR_HUMAN_REVIEW
    assert result.next_action == "RUN_VIDEO_BASE_E2E_THEN_FINALIZATION_E2E_HUMAN_REVIEW"
    assert result.finalization_complete is False
    assert result.publication_package_complete is False
    assert result.invokes_network is False
    assert result.authorization_to_publish is False
    assert result.uploads_files is False
    assert result.webhook_calls == 0
    assert result.marks_published is False


def test_declarative_approved_is_rejected_fail_closed():
    with pytest.raises(ValidationError, match="declarative APPROVED is not authoritative"):
        ProductionOrchestratorRequest(
            quality_gates=gates(),
            delivery=delivery(),
            video_base_manifest=video_manifest(),
            human_review_state=HumanReviewState.APPROVED,
        )


@pytest.mark.parametrize(
    "field",
    ["finalization_complete", "publication_package_complete"],
)
def test_declarative_downstream_completion_is_rejected(field):
    payload = {
        "quality_gates": gates(),
        "delivery": delivery(),
        "video_base_manifest": video_manifest(),
        field: True,
    }
    with pytest.raises(ValidationError, match="downstream evidence"):
        ProductionOrchestratorRequest(**payload)


def test_downstream_status_cannot_be_fabricated_as_orchestrator_plan():
    safe = build_production_orchestrator(
        ProductionOrchestratorRequest(
            quality_gates=gates(),
            delivery=delivery(),
            video_base_manifest=video_manifest(),
        )
    )
    payload = safe.model_dump()
    payload["status"] = ProductionOrchestratorStatus.READY_FOR_FINALIZATION

    with pytest.raises(ValidationError, match="downstream state requires"):
        ProductionOrchestratorPlan(**payload)
