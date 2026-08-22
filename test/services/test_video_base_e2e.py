from datetime import datetime, timezone
from app.models.production_orchestrator import HumanReviewState, ProductionOrchestratorPlan, ProductionOrchestratorStatus
from app.models.video_base_e2e import VideoBaseE2ERequest, VideoBaseE2EStatus
from app.services.video_base_e2e import build_video_base_e2e
NOW=datetime(2026,8,22,tzinfo=timezone.utc)

def orch(status=ProductionOrchestratorStatus.READY_FOR_VIDEO_BASE):
    return ProductionOrchestratorPlan(subject="Luna",source_plan_context_hash="ctx",source_quality_gates_hash="q",source_delivery_render_hash="d",status=status,next_action="x",quality_ready=True,delivery_ready=True,video_base_present=False,human_review_state=HumanReviewState.PENDING,finalization_complete=False,publication_package_complete=False,production_orchestrator_hash="o",generated_at_utc=NOW)

def test_waits_for_real_artifact():
    result=build_video_base_e2e(VideoBaseE2ERequest(orchestrator=orch()))
    assert result.status == VideoBaseE2EStatus.WAITING_FOR_REAL_VIDEO_BASE
    assert result.renders_video is False

def test_blocked_orchestrator_does_not_fake_e2e():
    result=build_video_base_e2e(VideoBaseE2ERequest(orchestrator=orch(ProductionOrchestratorStatus.BLOCKED_BY_QUALITY_OR_DELIVERY)))
    assert result.status == VideoBaseE2EStatus.WAITING_FOR_ORCHESTRATOR
