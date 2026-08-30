from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.delivery_render import DeliveryRenderStatus
from app.models.finalization_e2e import FinalizationE2EStatus, HumanFinalReviewDecision
from app.models.production_orchestrator import (
    HumanReviewState,
    PRODUCTION_ORCHESTRATOR_VERSION,
    ProductionOrchestratorPlan,
    ProductionOrchestratorRequest,
    ProductionOrchestratorStatus,
)
from app.models.publication_package import PublicationPackageStatus


def _hash(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_production_orchestrator(
    request: ProductionOrchestratorRequest,
) -> ProductionOrchestratorPlan:
    quality_ready = bool(request.quality_gates.technical_ready)
    delivery_ready = (
        request.delivery.status
        == DeliveryRenderStatus.READY_FOR_EXPLICIT_RENDER_APPROVAL
    )
    video_base_present = request.video_base_manifest is not None

    source_human_review_hash = (
        _hash(request.human_review.model_dump(mode="json"))
        if request.human_review is not None
        else None
    )
    source_finalization_e2e_hash = (
        request.finalization.finalization_e2e_hash
        if request.finalization is not None
        else None
    )
    source_publication_package_hash = (
        request.publication_package.publication_package_hash
        if request.publication_package is not None
        else None
    )

    if request.human_review is None:
        human_review_state = HumanReviewState.PENDING
    elif request.human_review.decision == HumanFinalReviewDecision.REJECT:
        human_review_state = HumanReviewState.REJECTED
    else:
        # The request model already rejects APPROVE unless all seven review gates pass.
        human_review_state = HumanReviewState.APPROVED

    finalization_complete = bool(
        request.finalization is not None
        and request.finalization.status == FinalizationE2EStatus.FINALIZATION_E2E_PASS
    )
    publication_package_complete = bool(
        request.publication_package is not None
        and request.publication_package.status
        == PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE
    )

    if not quality_ready or not delivery_ready:
        status = ProductionOrchestratorStatus.BLOCKED_BY_QUALITY_OR_DELIVERY
        next_action = "RESOLVE_EXISTING_QUALITY_OR_DELIVERY_GATES"
    elif not video_base_present:
        status = ProductionOrchestratorStatus.READY_FOR_VIDEO_BASE
        next_action = "RUN_EXISTING_F6_VIDEO_BASE_RENDER"
    elif human_review_state == HumanReviewState.PENDING:
        status = ProductionOrchestratorStatus.WAITING_FOR_HUMAN_REVIEW
        next_action = "HUMAN_REVIEW_VIDEO_BASE"
    elif human_review_state == HumanReviewState.REJECTED:
        status = ProductionOrchestratorStatus.HUMAN_REVIEW_REJECTED
        next_action = "RETURN_TO_EXISTING_CREATIVE_PIPELINE"
    elif not finalization_complete:
        status = ProductionOrchestratorStatus.READY_FOR_FINALIZATION
        next_action = "VERIFY_FINALIZATION_FROM_APPROVED_REVIEW_EVIDENCE"
    elif not publication_package_complete:
        status = ProductionOrchestratorStatus.READY_FOR_PUBLICATION_PACKAGE
        next_action = "BUILD_AND_VERIFY_MANUAL_PUBLICATION_PACKAGE"
    else:
        status = ProductionOrchestratorStatus.COMPLETE
        next_action = "PACKAGE_READY_AWAIT_EXPLICIT_MANUAL_PUBLICATION_DECISION"

    stable = {
        "version": PRODUCTION_ORCHESTRATOR_VERSION,
        "quality_hash": request.quality_gates.quality_gates_hash,
        "delivery_hash": request.delivery.delivery_render_hash,
        "video_base_sha": (
            request.video_base_manifest.final_video_sha256
            if request.video_base_manifest
            else None
        ),
        "human_review_hash": source_human_review_hash,
        "finalization_hash": source_finalization_e2e_hash,
        "publication_package_hash": source_publication_package_hash,
        "human_review_state": human_review_state.value,
        "finalization_complete": finalization_complete,
        "publication_package_complete": publication_package_complete,
        "status": status.value,
        "next_action": next_action,
    }

    return ProductionOrchestratorPlan(
        subject=request.quality_gates.subject,
        source_plan_context_hash=request.quality_gates.source_plan_context_hash,
        source_quality_gates_hash=request.quality_gates.quality_gates_hash,
        source_delivery_render_hash=request.delivery.delivery_render_hash,
        source_human_review_hash=source_human_review_hash,
        source_finalization_e2e_hash=source_finalization_e2e_hash,
        source_publication_package_hash=source_publication_package_hash,
        status=status,
        next_action=next_action,
        quality_ready=quality_ready,
        delivery_ready=delivery_ready,
        video_base_present=video_base_present,
        human_review_state=human_review_state,
        finalization_complete=finalization_complete,
        publication_package_complete=publication_package_complete,
        production_orchestrator_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
