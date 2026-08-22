from datetime import datetime, timezone
from app.models.finalization_e2e import FinalizationE2ERequest, FinalizationE2EStatus
from app.models.video_base_e2e import VideoBaseE2EPlan, VideoBaseE2EStatus
from app.services.finalization_e2e import build_finalization_e2e
NOW=datetime(2026,8,22,tzinfo=timezone.utc)
def base(status=VideoBaseE2EStatus.WAITING_FOR_REAL_VIDEO_BASE):
    return VideoBaseE2EPlan(source_production_orchestrator_hash="o",status=status,real_artifact_present=status==VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS,check_count=0,passed_count=0,failed_count=0,checks=[],video_base_e2e_hash="b",generated_at_utc=NOW)
def test_cannot_skip_real_video_base():
    r=build_finalization_e2e(FinalizationE2ERequest(video_base=base()))
    assert r.status==FinalizationE2EStatus.WAITING_FOR_VIDEO_BASE_E2E
    assert r.renders_video is False
def test_passed_base_still_requires_human_review():
    r=build_finalization_e2e(FinalizationE2ERequest(video_base=base(VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS)))
    assert r.status==FinalizationE2EStatus.WAITING_FOR_HUMAN_REVIEW
