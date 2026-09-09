from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.analytics_import_adapter import AnalyticsImportStatus
from app.models.golden_e2e_certification import GoldenCertificationStatus
from app.models.operational_hardening import OperationalHardeningStatus
from app.models.publication_package import (
    PUBLICATION_PACKAGE_VERSION,
    PublicationPackageStatus,
)
from app.models.quality_certification import CertificationStatus
from app.models.v1_readiness_audit import (
    V1_READINESS_AUDIT_VERSION,
    V1ReadinessAuditPlan,
    V1ReadinessCheck,
    V1ReadinessRequest,
    V1ReadinessStatus,
)
from app.services.centinela.pipeline_audit import evaluate_pipeline_audit
from app.services.centinela.quality_to_10_gate import canonical_quality_requirements


def _hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(payload).hexdigest().upper()


def _analytics_adapter_operational(request: V1ReadinessRequest) -> bool:
    plan = request.analytics_import
    return (
        plan.deterministic
        and plan.adapter_only
        and plan.resource_class == "LIGHT"
        and plan.network_calls == 0
        and plan.api_calls == 0
        and plan.database_writes == 0
        and not plan.credentials_required
        and not plan.uses_llm
        and not plan.auto_publication
        and bool(plan.analytics_import_hash.strip())
        and plan.status
        in {
            AnalyticsImportStatus.WAITING_FOR_IMPORT_DATA,
            AnalyticsImportStatus.IMPORT_READY,
        }
    )


def _publication_package_ready(request: V1ReadinessRequest) -> bool:
    plan = request.publication
    required = [asset for asset in plan.assets if asset.required]
    expected_ids = {
        "master",
        "social",
        "thumbnail",
        "subtitles_es",
        "caption",
        "metadata",
        "provenance",
        "publication_checklist",
    }
    return (
        plan.version == PUBLICATION_PACKAGE_VERSION
        and plan.status == PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE
        and plan.deterministic
        and plan.planning_only
        and plan.manual_publication_only
        and plan.resource_class == "LIGHT"
        and not plan.writes_files
        and not plan.uploads_files
        and plan.network_calls == 0
        and plan.webhook_calls == 0
        and not plan.auto_publication
        and not plan.authorization_to_publish
        and not plan.marks_published
        and plan.human_review_required
        and plan.local_final_certification_required
        and plan.metadata_present
        and plan.human_review_recorded
        and plan.finalization_evidence_valid
        and plan.rights_ready
        and plan.asset_count == 8
        and plan.required_asset_count == 8
        and plan.present_required_asset_count == 8
        and plan.hashed_required_asset_count == 8
        and plan.all_required_assets_present
        and plan.all_required_assets_hashed
        and len(required) == 8
        and {asset.asset_id for asset in required} == expected_ids
        and all(asset.present for asset in required)
        and all(asset.sha256 and len(asset.sha256) == 64 for asset in required)
        and bool(plan.source_finalization_e2e_hash.strip())
        and bool(plan.publication_package_hash.strip())
    )


def _quality_to_ten_complete(request: V1ReadinessRequest) -> bool:
    report = request.quality_to_ten
    if report is None or not report.all_dimensions_certified_10:
        return False

    expected = canonical_quality_requirements()
    expected_by_id = {item.dimension: item for item in expected}
    actual_ids = [item.requirement.dimension for item in report.dimensions]

    if len(expected_by_id) != 12:
        return False
    if len(actual_ids) != len(expected_by_id):
        return False
    if len(actual_ids) != len(set(actual_ids)):
        return False
    if set(actual_ids) != set(expected_by_id):
        return False

    for item in report.dimensions:
        if item.status != CertificationStatus.CERTIFIED_10:
            return False
        expected_requirement = expected_by_id[item.requirement.dimension]
        if item.requirement.model_dump(mode="json") != expected_requirement.model_dump(
            mode="json"
        ):
            return False

    return True


def _machine_oss_gate(request: V1ReadinessRequest):
    if request.pipeline_audit_manifest is None:
        return None
    return evaluate_pipeline_audit(request.pipeline_audit_manifest)


def _recovery_verified(request: V1ReadinessRequest) -> bool:
    manifest = request.recovery_manifest
    verification = request.recovery_verification
    if manifest is None or verification is None:
        return False
    if not verification.verified or verification.blockers:
        return False
    if verification.required_total != verification.required_passed:
        return False

    required = {item.artifact_id: item for item in manifest.artifacts if item.required}
    if verification.required_total != len(required):
        return False

    verified_items = {item.artifact_id: item for item in verification.items}
    if len(verified_items) != len(verification.items):
        return False

    for artifact_id, expected in required.items():
        actual = verified_items.get(artifact_id)
        if actual is None or not actual.exists or not actual.hash_matches:
            return False
        if actual.relative_path.casefold() != expected.relative_path.casefold():
            return False
        if not actual.actual_sha256:
            return False
        if actual.actual_sha256.casefold() != expected.sha256.casefold():
            return False
    return True


def _identity_consistent(request: V1ReadinessRequest) -> bool:
    target = (request.release_candidate_sha or "").strip().lower()
    if not target:
        return False

    identities = [
        request.quality_to_ten.release_candidate_sha
        if request.quality_to_ten is not None
        else None,
        request.pipeline_audit_manifest.project_sha
        if request.pipeline_audit_manifest is not None
        else None,
        request.recovery_manifest.release_candidate_sha
        if request.recovery_manifest is not None
        else None,
        request.recovery_verification.release_candidate_sha
        if request.recovery_verification is not None
        else None,
    ]
    return all(value is not None and value.lower() == target for value in identities)


def build_v1_readiness_audit(request: V1ReadinessRequest) -> V1ReadinessAuditPlan:
    legacy_oss_complete = bool(request.oss_audit) and all(
        item.verified for item in request.oss_audit
    )
    analytics_operational = _analytics_adapter_operational(request)
    publication_ready = _publication_package_ready(request)
    quality_complete = _quality_to_ten_complete(request)
    machine_oss = _machine_oss_gate(request)
    machine_oss_complete = bool(machine_oss and machine_oss.pass_gate)
    recovery_verified = _recovery_verified(request)
    identity_consistent = _identity_consistent(request)

    quality_dimension_count = (
        len(request.quality_to_ten.dimensions)
        if request.quality_to_ten is not None
        else 0
    )

    checks = [
        V1ReadinessCheck(
            check_id="operational_hardening_not_blocked",
            passed=(
                request.hardening.status
                != OperationalHardeningStatus.HARDENING_BLOCKED
            ),
            detail=request.hardening.status.value,
        ),
        V1ReadinessCheck(
            check_id="golden_real_e2e_certified",
            passed=(
                request.golden.status
                == GoldenCertificationStatus.CERTIFICATION_PASS
            ),
            detail=request.golden.status.value,
        ),
        V1ReadinessCheck(
            check_id="manual_publication_package_ready",
            passed=publication_ready,
            detail=(
                f"status={request.publication.status.value};"
                f"canonical_v0_2={'pass' if publication_ready else 'fail'};"
                "auto_publication=false"
            ),
        ),
        V1ReadinessCheck(
            check_id="analytics_adapter_operational",
            passed=analytics_operational,
            detail=(
                f"status={request.analytics_import.status.value};"
                "real_channel_data_required=false;"
                f"mechanism_guardrails={'pass' if analytics_operational else 'fail'}"
            ),
        ),
        V1ReadinessCheck(
            check_id="oss_audit_complete",
            passed=legacy_oss_complete,
            blocking=False,
            detail=(
                "legacy_informational_only=true;"
                f"verified={sum(item.verified for item in request.oss_audit)}"
                f"/{len(request.oss_audit)}"
            ),
        ),
        V1ReadinessCheck(
            check_id="quality_to_ten_complete",
            passed=quality_complete,
            detail=(
                f"present={str(request.quality_to_ten is not None).lower()};"
                f"dimensions={quality_dimension_count}/12;"
                f"canonical_contract={'pass' if quality_complete else 'fail'};"
                f"all_dimensions_certified_10={str(quality_complete).lower()}"
            ),
        ),
        V1ReadinessCheck(
            check_id="machine_readable_oss_audit_complete",
            passed=machine_oss_complete,
            detail=(
                f"present={str(request.pipeline_audit_manifest is not None).lower()};"
                f"pass_gate={str(machine_oss_complete).lower()};"
                f"blockers={0 if machine_oss is None else len(machine_oss.blockers)}"
            ),
        ),
        V1ReadinessCheck(
            check_id="recovery_verified",
            passed=recovery_verified,
            detail=(
                f"manifest_present={str(request.recovery_manifest is not None).lower()};"
                f"verification_present={str(request.recovery_verification is not None).lower()};"
                f"verified={str(recovery_verified).lower()}"
            ),
        ),
        V1ReadinessCheck(
            check_id="release_candidate_identity_consistent",
            passed=identity_consistent,
            detail=(
                f"target={request.release_candidate_sha or 'MISSING'};"
                f"consistent={str(identity_consistent).lower()}"
            ),
        ),
    ]

    technical = all(item.passed for item in checks if item.blocking)
    if not technical:
        status = V1ReadinessStatus.NOT_READY_FOR_ARCHITECTURE_FREEZE
        authorized = False
    elif not request.human_freeze_approval:
        status = V1ReadinessStatus.READY_FOR_HUMAN_FREEZE_APPROVAL
        authorized = False
    else:
        status = V1ReadinessStatus.ARCHITECTURE_FREEZE_AUTHORIZED
        authorized = True

    stable = {
        "version": V1_READINESS_AUDIT_VERSION,
        "release_candidate_sha": request.release_candidate_sha,
        "orchestrator": request.orchestrator.production_orchestrator_hash,
        "publication": request.publication.publication_package_hash,
        "analytics": request.analytics_import.analytics_import_hash,
        "hardening": request.hardening.operational_hardening_hash,
        "golden": request.golden.golden_e2e_hash,
        "legacy_oss": [item.model_dump(mode="json") for item in request.oss_audit],
        "quality_to_ten": (
            request.quality_to_ten.model_dump(mode="json")
            if request.quality_to_ten is not None
            else None
        ),
        "pipeline_audit_manifest": (
            request.pipeline_audit_manifest.model_dump(mode="json")
            if request.pipeline_audit_manifest is not None
            else None
        ),
        "machine_oss_result": (
            machine_oss.model_dump(mode="json") if machine_oss is not None else None
        ),
        "recovery_manifest": (
            request.recovery_manifest.model_dump(mode="json")
            if request.recovery_manifest is not None
            else None
        ),
        "recovery_verification": (
            request.recovery_verification.model_dump(mode="json")
            if request.recovery_verification is not None
            else None
        ),
        "human_freeze_approval": request.human_freeze_approval,
        "status": status.value,
    }

    return V1ReadinessAuditPlan(
        status=status,
        freeze_authorized=authorized,
        release_candidate_sha=request.release_candidate_sha,
        quality_to_ten_complete=quality_complete,
        machine_readable_oss_audit_complete=machine_oss_complete,
        recovery_verified=recovery_verified,
        release_candidate_identity_consistent=identity_consistent,
        check_count=len(checks),
        passed_count=sum(item.passed for item in checks),
        failed_count=sum(not item.passed for item in checks),
        checks=checks,
        oss_audit_count=len(request.oss_audit),
        oss_audit_verified_count=sum(item.verified for item in request.oss_audit),
        oss_audit=request.oss_audit,
        v1_readiness_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
