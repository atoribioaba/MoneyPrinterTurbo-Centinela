from datetime import datetime,timezone
from app.models.analytics_import_adapter import AnalyticsImportPlan, AnalyticsImportStatus
from app.models.analytics_brain import AnalyticsBrainRequest
from app.models.golden_e2e_certification import GoldenE2ECertificationPlan, GoldenCertificationStatus
from app.models.operational_hardening import OperationalEnvironmentSnapshot, OperationalHardeningPlan, OperationalHardeningStatus
from app.models.production_orchestrator import HumanReviewState, ProductionOrchestratorPlan, ProductionOrchestratorStatus
from app.models.publication_package import PublicationPackagePlan, PublicationPackageStatus
from app.models.v1_readiness_audit import V1ReadinessRequest, V1ReadinessStatus
from app.services.v1_readiness_audit import build_v1_readiness_audit
NOW=datetime(2026,8,22,tzinfo=timezone.utc)
def fixtures():
    o=ProductionOrchestratorPlan(subject="L",source_plan_context_hash="c",source_quality_gates_hash="q",source_delivery_render_hash="d",status=ProductionOrchestratorStatus.READY_FOR_VIDEO_BASE,next_action="x",quality_ready=True,delivery_ready=True,video_base_present=False,human_review_state=HumanReviewState.PENDING,finalization_complete=False,publication_package_complete=False,production_orchestrator_hash="o",generated_at_utc=NOW)
    p=PublicationPackagePlan(source_finalization_e2e_hash="f",status=PublicationPackageStatus.WAITING_FOR_FINALIZATION,asset_count=0,assets=[],metadata_present=False,publication_package_hash="p",generated_at_utc=NOW)
    a=AnalyticsImportPlan(status=AnalyticsImportStatus.WAITING_FOR_IMPORT_DATA,row_count=0,observation_count=0,observations=[],analytics_request=AnalyticsBrainRequest(),analytics_import_hash="a",generated_at_utc=NOW)
    s=OperationalEnvironmentSnapshot(repo_exists=True,venv_python_exists=True,git_present=True,ffmpeg_present=True,gitleaks_present=True,certifier_present=True,backup_root_exists=True,resource_governor_available=True,free_space_gb=100,backup_bundle_count=1)
    h=OperationalHardeningPlan(status=OperationalHardeningStatus.HARDENING_PASS,safe_to_run_pipeline=True,finding_count=0,block_count=0,warning_count=0,findings=[],snapshot=s,operational_hardening_hash="h",generated_at_utc=NOW)
    g=GoldenE2ECertificationPlan(status=GoldenCertificationStatus.WAITING_FOR_REAL_E2E,scenario_count=0,passed_scenario_count=0,missing_scenarios=[],performance_present=False,golden_e2e_hash="g",generated_at_utc=NOW)
    return o,p,a,h,g
def test_never_freezes_without_real_e2e():
    o,p,a,h,g=fixtures(); r=build_v1_readiness_audit(V1ReadinessRequest(orchestrator=o,publication=p,analytics_import=a,hardening=h,golden=g))
    assert r.status==V1ReadinessStatus.NOT_READY_FOR_ARCHITECTURE_FREEZE
    assert r.architecture_v1_frozen is False
    assert r.freeze_executed is False
