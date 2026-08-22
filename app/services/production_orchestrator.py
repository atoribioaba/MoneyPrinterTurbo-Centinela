from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.delivery_render import DeliveryRenderStatus
from app.models.production_orchestrator import (
    HumanReviewState,
    PRODUCTION_ORCHESTRATOR_VERSION,
    ProductionOrchestratorPlan,
    ProductionOrchestratorRequest,
    ProductionOrchestratorStatus,
)


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_production_orchestrator(request: ProductionOrchestratorRequest) -> ProductionOrchestratorPlan:
    quality_ready = bool(request.quality_gates.technical_ready)
    delivery_ready = request.delivery.status == DeliveryRenderStatus.READY_FOR_EXPLICIT_RENDER_APPROVAL
    video_base_present = request.video_base_manifest is not None

    if not quality_ready or not delivery_ready:
        status = ProductionOrchestratorStatus.BLOCKED_BY_QUALITY_OR_DELIVERY
        next_action = "RESOLVE_EXISTING_QUALITY_OR_DELIVERY_GATES"
    elif not video_base_present:
        status = ProductionOrchestratorStatus.READY_FOR_VIDEO_BASE
        next_action = "RUN_EXISTING_F6_VIDEO_BASE_RENDER"
    elif request.human_review_state == HumanReviewState.PENDING:
        status = ProductionOrchestratorStatus.WAITING_FOR_HUMAN_REVIEW
        next_action = "HUMAN_REVIEW_VIDEO_BASE"
    elif request.human_review_state == HumanReviewState.REJECTED:
        status = ProductionOrchestratorStatus.HUMAN_REVIEW_REJECTED
        next_action = "RETURN_TO_EXISTING_CREATIVE_PIPELINE"
    elif not request.finalization_complete:
        status = ProductionOrchestratorStatus.READY_FOR_FINALIZATION
        next_action = "FINALIZE_APPROVED_VIDEO"
    elif not request.publication_package_complete:
        status = ProductionOrchestratorStatus.READY_FOR_PUBLICATION_PACKAGE
        next_action = "BUILD_MANUAL_PUBLICATION_PACKAGE"
    else:
        status = ProductionOrchestratorStatus.COMPLETE
        next_action = "MANUAL_PUBLICATION_OR_ANALYTICS_BINDING"

    stable = {
        "version": PRODUCTION_ORCHESTRATOR_VERSION,
        "quality_hash": request.quality_gates.quality_gates_hash,
        "delivery_hash": request.delivery.delivery_render_hash,
        "video_base_sha": request.video_base_manifest.final_video_sha256 if request.video_base_manifest else None,
        "human_review_state": request.human_review_state.value,
        "finalization_complete": request.finalization_complete,
        "publication_package_complete": request.publication_package_complete,
        "status": status.value,
        "next_action": next_action,
    }

    return ProductionOrchestratorPlan(
        subject=request.quality_gates.subject,
        source_plan_context_hash=request.quality_gates.source_plan_context_hash,
        source_quality_gates_hash=request.quality_gates.quality_gates_hash,
        source_delivery_render_hash=request.delivery.delivery_render_hash,
        status=status,
        next_action=next_action,
        quality_ready=quality_ready,
        delivery_ready=delivery_ready,
        video_base_present=video_base_present,
        human_review_state=request.human_review_state,
        finalization_complete=request.finalization_complete,
        publication_package_complete=request.publication_package_complete,
        production_orchestrator_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
