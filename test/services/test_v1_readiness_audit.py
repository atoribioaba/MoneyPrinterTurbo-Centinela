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
from app.models.pipeline_audit import (
    OpenSourceClassification,
    PipelineAuditManifest,
    PipelineComponentAudit,
    PipelineDecision,
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
from app.models.quality_certification import (
    CertificationEvidence,
    CertificationStatus,
    DimensionCertification,
    DimensionRequirement,
    EvidenceKind,
    QualityToTenReport,
)
from app.models.recovery import (
    RecoveryArtifact,
    RecoveryArtifactKind,
    RecoveryManifest,
    RecoveryVerificationItem,
    RecoveryVerificationResult,
)
from app.models.v1_readiness_audit import (
    OSSAuditEntry,
    V1ReadinessRequest,
    V1ReadinessStatus,
)
from app.services.centinela.pipeline_audit import REQUIRED_V1_FUNCTIONS
from app.services.centinela.quality_to_10_gate import (
    build_quality_report,
    canonical_quality_requirements,
)
from app.services.v1_readiness_audit import build_v1_readiness_audit

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)
HASH = "A" * 64
RC_SHA = "1" * 40


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


def certified_quality_report(*, release_candidate_sha=RC_SHA):
    dimensions = []
    for requirement in canonical_quality_requirements():
        evidence = []
        for kind in sorted(requirement.required_evidence_kinds, key=lambda item: item.value):
            evidence.append(
                CertificationEvidence(
                    evidence_id=f"{requirement.dimension}:{kind.value}",
                    kind=kind,
                    ref=f"fixture:{requirement.dimension}:{kind.value}",
                    sha256=HASH,
                    description="synthetic F58 v0.2 certification fixture",
                    physical_pc=(
                        requirement.requires_physical_pc
                        and kind != EvidenceKind.HUMAN_REVIEW
                    ),
                    human_review=(
                        requirement.requires_human_review
                        and kind == EvidenceKind.HUMAN_REVIEW
                    ),
                )
            )
        dimensions.append((requirement, evidence))
    return build_quality_report(
        release_candidate_sha=release_candidate_sha,
        dimensions=dimensions,
    )


def passing_pipeline_audit(*, release_candidate_sha=RC_SHA):
    components = [
        PipelineComponentAudit(
            component_id=f"fixture-{function_id}",
            function_id=function_id,
            component=f"fixture {function_id}",
            classification=OpenSourceClassification.OPEN_SOURCE_FREE,
            decision=PipelineDecision.KEEP,
            license_id_or_status="TEST-ONLY",
            source_url=f"https://example.invalid/{function_id}",
            selected_for_rc=True,
            version_or_commit="fixture-v1",
            artifact_sha256=HASH,
            weights_or_binary_artifact=True,
            physical_validation_required=True,
            physical_evidence_ids=[f"physical:{function_id}"],
        )
        for function_id in sorted(REQUIRED_V1_FUNCTIONS)
    ]
    return PipelineAuditManifest(
        project_sha=release_candidate_sha,
        created_at=NOW,
        components=components,
        auto_publication=False,
    )


def passing_recovery(*, release_candidate_sha=RC_SHA):
    manifest = RecoveryManifest(
        release_candidate_sha=release_candidate_sha,
        artifacts=[
            RecoveryArtifact(
                artifact_id="uv-lock",
                kind=RecoveryArtifactKind.LOCKFILE,
                relative_path="uv.lock",
                sha256=HASH,
            )
        ],
        auto_publication=False,
    )
    verification = RecoveryVerificationResult(
        release_candidate_sha=release_candidate_sha,
        verified=True,
        required_total=1,
        required_passed=1,
        items=[
            RecoveryVerificationItem(
                artifact_id="uv-lock",
                relative_path="uv.lock",
                exists=True,
                hash_matches=True,
                actual_sha256=HASH,
            )
        ],
        blockers=[],
    )
    return manifest, verification


def technically_ready_request(*, human_freeze_approval=False):
    orchestrator, _, analytics, hardening, golden = fixtures()
    golden = golden.model_copy(
        update={"status": GoldenCertificationStatus.CERTIFICATION_PASS}
    )
    recovery_manifest, recovery_verification = passing_recovery()
    return V1ReadinessRequest(
        orchestrator=orchestrator,
        publication=ready_publication(),
        analytics_import=analytics,
        hardening=hardening,
        golden=golden,
        release_candidate_sha=RC_SHA,
        quality_to_ten=certified_quality_report(),
        pipeline_audit_manifest=passing_pipeline_audit(),
        recovery_manifest=recovery_manifest,
        recovery_verification=recovery_verification,
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
    assert result.quality_to_ten_complete is True
    assert result.machine_readable_oss_audit_complete is True
    assert result.recovery_verified is True
    assert result.release_candidate_identity_consistent is True
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


def test_legacy_oss_audit_is_informational_only():
    request = technically_ready_request()
    request = request.model_copy(update={"oss_audit": []})
    result = build_v1_readiness_audit(request)
    check = next(item for item in result.checks if item.check_id == "oss_audit_complete")
    assert check.passed is False
    assert check.blocking is False
    assert result.status == V1ReadinessStatus.READY_FOR_HUMAN_FREEZE_APPROVAL
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


def test_quality_gate_rejects_partial_report_even_when_summary_is_true():
    request = technically_ready_request()
    full = certified_quality_report()
    partial = QualityToTenReport(
        release_candidate_sha=RC_SHA,
        dimensions=[full.dimensions[0]],
        all_dimensions_certified_10=True,
    )
    request = request.model_copy(update={"quality_to_ten": partial})
    result = build_v1_readiness_audit(request)
    check = next(item for item in result.checks if item.check_id == "quality_to_ten_complete")
    assert check.passed is False
    assert "dimensions=1/12" in check.detail
    assert result.status == V1ReadinessStatus.NOT_READY_FOR_ARCHITECTURE_FREEZE


def test_quality_gate_rejects_duplicate_dimension_ids():
    request = technically_ready_request()
    full = certified_quality_report()
    dimensions = list(full.dimensions)
    dimensions[-1] = dimensions[0]
    duplicate = QualityToTenReport(
        release_candidate_sha=RC_SHA,
        dimensions=dimensions,
        all_dimensions_certified_10=True,
    )
    request = request.model_copy(update={"quality_to_ten": duplicate})
    result = build_v1_readiness_audit(request)
    check = next(item for item in result.checks if item.check_id == "quality_to_ten_complete")
    assert check.passed is False
    assert result.status == V1ReadinessStatus.NOT_READY_FOR_ARCHITECTURE_FREEZE


def test_quality_gate_rejects_weakened_canonical_requirement():
    request = technically_ready_request()
    full = certified_quality_report()
    weakened = DimensionCertification(
        requirement=DimensionRequirement(dimension="windows_physical"),
        evidence=[],
        status=CertificationStatus.CERTIFIED_10,
    )
    dimensions = [
        weakened if item.requirement.dimension == "windows_physical" else item
        for item in full.dimensions
    ]
    forged = QualityToTenReport(
        release_candidate_sha=RC_SHA,
        dimensions=dimensions,
        all_dimensions_certified_10=True,
    )
    request = request.model_copy(update={"quality_to_ten": forged})
    result = build_v1_readiness_audit(request)
    check = next(item for item in result.checks if item.check_id == "quality_to_ten_complete")
    assert check.passed is False
    assert "canonical_contract=fail" in check.detail
    assert result.status == V1ReadinessStatus.NOT_READY_FOR_ARCHITECTURE_FREEZE


def test_release_candidate_identity_mismatch_fails_closed():
    request = technically_ready_request()
    mismatched_audit = passing_pipeline_audit(release_candidate_sha="2" * 40)
    request = request.model_copy(update={"pipeline_audit_manifest": mismatched_audit})
    result = build_v1_readiness_audit(request)
    check = next(
        item
        for item in result.checks
        if item.check_id == "release_candidate_identity_consistent"
    )
    assert check.passed is False
    assert result.status == V1ReadinessStatus.NOT_READY_FOR_ARCHITECTURE_FREEZE


def test_readiness_hash_is_deterministic_for_same_evidence():
    request = technically_ready_request()
    first = build_v1_readiness_audit(request)
    second = build_v1_readiness_audit(request)
    assert first.v1_readiness_hash == second.v1_readiness_hash
