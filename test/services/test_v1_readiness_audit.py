from datetime import datetime, timezone

from app.models.analytics_brain import AnalyticsBrainRequest
from app.models.analytics_import_adapter import AnalyticsImportPlan, AnalyticsImportStatus
from app.models.golden_e2e_certification import (
    GoldenCertificationStatus,
    GoldenE2ECertificationPlan,
)
from app.models.operational_hardening import (
    OperationalEnvironmentSnapshot,
    OperationalHardeningPlan,
    OperationalHardeningStatus,
)
from app.models.production_orchestrator import (
    HumanReviewState,
    ProductionOrchestratorPlan,
    ProductionOrchestratorStatus,
)
from app.models.publication_package import (
    PackageAsset,
    PublicationPackagePlan,
    PublicationPackageStatus,
)
from app.models.v1_readiness_audit import (
    OSSAuditEntry,
    V1ReadinessRequest,
    V1ReadinessStatus,
)
from app.services.v1_readiness_audit import build_v1_readiness_audit

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)
HASH = "A" * 64


def ready_publication():
    assets = [
        PackageAsset(
            asset_id="master",
            source_path="synthetic/master.mp4",
            target_filename="master_2160x3840.mp4",
            present=True,
            sha256=HASH,
        ),
        PackageAsset(
            asset_id="social",
            source_path="synthetic/social.mp4",
            target_filename="social_1080x1920.mp4",
            present=True,
            sha256=HASH,
        ),
        PackageAsset(
            asset_id="thumbnail",
            source_path="synthetic/thumbnail.jpg",
            target_filename="thumbnail.jpg",
            present=True,
            sha256=HASH,
        ),
        PackageAsset(
            asset_id="subtitles_es",
            source_path="synthetic/subtitles-es.srt",
            target_filename="subtitles-es.srt",
            present=True,
            sha256=HASH,
        ),
        PackageAsset(
            asset_id="caption",
            target_filename="caption.txt",
            present=True,
            sha256=HASH,
            generated_from_metadata=True,
        ),
        PackageAsset(
            asset_id="metadata",
            target_filename="metadata.json",
            present=True,
            sha256=HASH,
            generated_from_metadata=True,
        ),
        PackageAsset(
            asset_id="provenance",
            source_path="synthetic/provenance.json",
            target_filename="sources-licenses-provenance.json",
            present=True,
            sha256=HASH,
        ),
        PackageAsset(
            asset_id="publication_checklist",
            source_path="synthetic/review-checklist.json",
            target_filename="publication-checklist.json",
            present=True,
            sha256=HASH,
        ),
    ]
    return PublicationPackagePlan(
        source_finalization_e2e_hash="F" * 64,
        status=PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE,
        asset_count=8,
        required_asset_count=8,
        present_required_asset_count=8,
        hashed_required_asset_count=8,
        assets=assets,
        metadata_present=True,
        human_review_recorded=True,
        finalization_evidence_valid=True,
        rights_ready=True,
        all_required_assets_present=True,
        all_required_assets_hashed=True,
        publication_package_hash="P" * 64,
        generated_at_utc=NOW,
    )


def fixtures():
    orchestrator = ProductionOrchestratorPlan(
        subject="L",
        source_plan_context_hash="c",
        source_quality_gates_hash="q",
        source_delivery_render_hash="d",
        status=ProductionOrchestratorStatus.READY_FOR_VIDEO_BASE,
        next_action="x",
        quality_ready=True,
        delivery_ready=True,
        video_base_present=False,
        human_review_state=HumanReviewState.PENDING,
        finalization_complete=False,
        publication_package_complete=False,
        production_orchestrator_hash="o",
        generated_at_utc=NOW,
    )
    publication = PublicationPackagePlan(
        source_finalization_e2e_hash="f",
        status=PublicationPackageStatus.WAITING_FOR_FINALIZATION,
        asset_count=0,
        assets=[],
        metadata_present=False,
        publication_package_hash="p",
        generated_at_utc=NOW,
    )
    analytics = AnalyticsImportPlan(
        status=AnalyticsImportStatus.WAITING_FOR_IMPORT_DATA,
        row_count=0,
        observation_count=0,
        observations=[],
        analytics_request=AnalyticsBrainRequest(),
        analytics_import_hash="a",
        generated_at_utc=NOW,
    )
    snapshot = OperationalEnvironmentSnapshot(
        repo_exists=True,
        venv_python_exists=True,
        git_present=True,
        ffmpeg_present=True,
        gitleaks_present=True,
        certifier_present=True,
        backup_root_exists=True,
        resource_governor_available=True,
        free_space_gb=100,
        backup_bundle_count=1,
    )
    hardening = OperationalHardeningPlan(
        status=OperationalHardeningStatus.HARDENING_PASS,
        safe_to_run_pipeline=True,
        finding_count=0,
        block_count=0,
        warning_count=0,
        findings=[],
        snapshot=snapshot,
        operational_hardening_hash="h",
        generated_at_utc=NOW,
    )
    golden = GoldenE2ECertificationPlan(
        status=GoldenCertificationStatus.WAITING_FOR_REAL_E2E,
        scenario_count=0,
        passed_scenario_count=0,
        missing_scenarios=[],
        performance_present=False,
        golden_e2e_hash="g",
        generated_at_utc=NOW,
    )
    return orchestrator, publication, analytics, hardening, golden


def verified_oss_audit():
    return [
        OSSAuditEntry(
            function="video/audio",
            current_component="FFmpeg",
            classification="OPEN SOURCE + 100 % GRATUITA",
            free=True,
            license="LGPL-2.1+; exact local build pending final verification",
            decision="MANTENER",
            verified=True,
        )
    ]


def technically_ready_request(*, human_freeze_approval=False):
    orchestrator, _, analytics, hardening, golden = fixtures()
    golden = golden.model_copy(
        update={"status": GoldenCertificationStatus.CERTIFICATION_PASS}
    )
    return V1ReadinessRequest(
        orchestrator=orchestrator,
        publication=ready_publication(),
        analytics_import=analytics,
        hardening=hardening,
        golden=golden,
        oss_audit=verified_oss_audit(),
        human_freeze_approval=human_freeze_approval,
    )


def test_never_freezes_without_real_e2e():
    orchestrator, publication, analytics, hardening, golden = fixtures()
    result = build_v1_readiness_audit(
        V1ReadinessRequest(
            orchestrator=orchestrator,
            publication=publication,
            analytics_import=analytics,
            hardening=hardening,
            golden=golden,
        )
    )
    assert result.status == V1ReadinessStatus.NOT_READY_FOR_ARCHITECTURE_FREEZE
    assert result.architecture_v1_frozen is False
    assert result.freeze_executed is False
    assert result.freeze_authorized is False


def test_all_technical_gates_require_human_freeze_approval():
    result = build_v1_readiness_audit(technically_ready_request())
    assert result.status == V1ReadinessStatus.READY_FOR_HUMAN_FREEZE_APPROVAL
    assert result.failed_count == 0
    assert result.freeze_authorized is False
    assert result.architecture_v1_frozen is False
    assert result.freeze_executed is False
    assert result.auto_publication is False
    assert result.auto_activation is False
    assert result.writes_runtime_config is False


def test_human_approval_authorizes_but_never_executes_freeze():
    result = build_v1_readiness_audit(
        technically_ready_request(human_freeze_approval=True)
    )
    assert result.status == V1ReadinessStatus.ARCHITECTURE_FREEZE_AUTHORIZED
    assert result.freeze_authorized is True
    assert result.architecture_v1_frozen is False
    assert result.freeze_executed is False
    assert result.auto_publication is False
    assert result.auto_activation is False
    assert result.writes_runtime_config is False


def test_incomplete_oss_audit_fails_closed():
    request = technically_ready_request()
    request = request.model_copy(update={"oss_audit": []})
    result = build_v1_readiness_audit(request)
    assert result.status == V1ReadinessStatus.NOT_READY_FOR_ARCHITECTURE_FREEZE
    check = next(item for item in result.checks if item.check_id == "oss_audit_complete")
    assert check.passed is False
    assert result.freeze_authorized is False


def test_publication_package_not_ready_fails_closed():
    orchestrator, publication, analytics, hardening, golden = fixtures()
    request = V1ReadinessRequest(
        orchestrator=orchestrator,
        publication=publication,
        analytics_import=analytics,
        hardening=hardening,
        golden=golden,
    )
    result = build_v1_readiness_audit(request)
    check = next(
        item
        for item in result.checks
        if item.check_id == "manual_publication_package_ready"
    )
    assert check.passed is False
    assert "canonical_v0_2=fail" in check.detail
    assert result.freeze_authorized is False


def test_forged_publication_ready_evidence_fails_closed():
    request = technically_ready_request()
    forged = request.publication.model_copy(
        update={"all_required_assets_hashed": False}
    )
    request = request.model_copy(update={"publication": forged})
    result = build_v1_readiness_audit(request)
    check = next(
        item
        for item in result.checks
        if item.check_id == "manual_publication_package_ready"
    )
    assert check.passed is False
    assert result.status == V1ReadinessStatus.NOT_READY_FOR_ARCHITECTURE_FREEZE
    assert result.freeze_authorized is False


def test_waiting_for_real_channel_analytics_does_not_block_mechanism_gate():
    request = technically_ready_request()
    assert request.analytics_import.status == AnalyticsImportStatus.WAITING_FOR_IMPORT_DATA
    result = build_v1_readiness_audit(request)
    check = next(
        item for item in result.checks if item.check_id == "analytics_adapter_operational"
    )
    assert check.passed is True
    assert "real_channel_data_required=false" in check.detail
    assert result.status == V1ReadinessStatus.READY_FOR_HUMAN_FREEZE_APPROVAL


def test_broken_analytics_mechanism_evidence_fails_closed():
    request = technically_ready_request()
    broken_analytics = request.analytics_import.model_copy(
        update={"analytics_import_hash": ""}
    )
    request = request.model_copy(update={"analytics_import": broken_analytics})
    result = build_v1_readiness_audit(request)
    check = next(
        item for item in result.checks if item.check_id == "analytics_adapter_operational"
    )
    assert check.passed is False
    assert "mechanism_guardrails=fail" in check.detail
    assert result.status == V1ReadinessStatus.NOT_READY_FOR_ARCHITECTURE_FREEZE
    assert result.freeze_authorized is False


def test_readiness_hash_is_deterministic_for_same_evidence():
    request = technically_ready_request()
    first = build_v1_readiness_audit(request)
    second = build_v1_readiness_audit(request)
    assert first.v1_readiness_hash == second.v1_readiness_hash
