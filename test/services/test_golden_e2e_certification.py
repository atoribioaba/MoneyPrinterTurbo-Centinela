from datetime import datetime,timezone
from app.models.finalization_e2e import FinalizationE2EPlan, FinalizationE2EStatus
from app.models.golden_e2e_certification import GoldenE2ECertificationRequest, GoldenCertificationStatus
from app.models.operational_hardening import OperationalEnvironmentSnapshot, OperationalHardeningPlan, OperationalHardeningStatus
from app.models.video_base_e2e import VideoBaseE2EPlan, VideoBaseE2EStatus
from app.services.golden_e2e_certification import build_golden_e2e_certification
NOW=datetime(2026,8,22,tzinfo=timezone.utc)
def base(): return VideoBaseE2EPlan(source_production_orchestrator_hash="o",status=VideoBaseE2EStatus.WAITING_FOR_REAL_VIDEO_BASE,real_artifact_present=False,check_count=0,passed_count=0,failed_count=0,checks=[],video_base_e2e_hash="b",generated_at_utc=NOW)
def fin(): return FinalizationE2EPlan(source_video_base_e2e_hash="b",status=FinalizationE2EStatus.WAITING_FOR_VIDEO_BASE_E2E,human_review_recorded=False,artifact_count=0,check_count=0,passed_count=0,failed_count=0,checks=[],artifacts=[],finalization_e2e_hash="f",generated_at_utc=NOW)
def hard():
    s=OperationalEnvironmentSnapshot(repo_exists=True,venv_python_exists=True,git_present=True,ffmpeg_present=True,gitleaks_present=True,certifier_present=True,backup_root_exists=True,resource_governor_available=True,free_space_gb=100,backup_bundle_count=1)
    return OperationalHardeningPlan(status=OperationalHardeningStatus.HARDENING_PASS,safe_to_run_pipeline=True,finding_count=0,block_count=0,warning_count=0,findings=[],snapshot=s,operational_hardening_hash="h",generated_at_utc=NOW)
def test_real_video_is_mandatory():
    r=build_golden_e2e_certification(GoldenE2ECertificationRequest(video_base=base(),finalization=fin(),hardening=hard()))
    assert r.status==GoldenCertificationStatus.WAITING_FOR_REAL_E2E
    assert r.synthetic_only_not_accepted is True
