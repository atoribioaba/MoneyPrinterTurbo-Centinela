from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.golden_e2e_certification import GoldenCertificationStatus
from app.models.operational_hardening import OperationalHardeningStatus
from app.models.publication_package import PublicationPackageStatus
from app.models.v1_readiness_audit import (
    V1_READINESS_AUDIT_VERSION,
    V1ReadinessAuditPlan,
    V1ReadinessCheck,
    V1ReadinessRequest,
    V1ReadinessStatus,
)


def _hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(payload).hexdigest().upper()


def build_v1_readiness_audit(request: V1ReadinessRequest) -> V1ReadinessAuditPlan:
    oss_complete = bool(request.oss_audit) and all(
        item.verified for item in request.oss_audit
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
            passed=(
                request.publication.status
                == PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE
            ),
            detail=request.publication.status.value,
        ),
        V1ReadinessCheck(
            check_id="analytics_adapter_operational",
            passed=True,
            detail=request.analytics_import.status.value,
        ),
        V1ReadinessCheck(
            check_id="oss_audit_complete",
            passed=oss_complete,
            detail=(
                f"verified={sum(item.verified for item in request.oss_audit)}"
                f"/{len(request.oss_audit)}"
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
        "orchestrator": request.orchestrator.production_orchestrator_hash,
        "publication": request.publication.publication_package_hash,
        "analytics": request.analytics_import.analytics_import_hash,
        "hardening": request.hardening.operational_hardening_hash,
        "golden": request.golden.golden_e2e_hash,
        "oss": [item.model_dump(mode="json") for item in request.oss_audit],
        "human_freeze_approval": request.human_freeze_approval,
        "status": status.value,
    }

    return V1ReadinessAuditPlan(
        status=status,
        freeze_authorized=authorized,
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
