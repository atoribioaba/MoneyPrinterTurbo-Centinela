from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.delivery_render import DeliveryRenderPlan
from app.models.quality_gates import QualityGatesPlan
from app.models.video_base import VideoBaseRenderManifest

PRODUCTION_ORCHESTRATOR_VERSION = "production-orchestrator-v0.2"


class StrictProductionOrchestratorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class HumanReviewState(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ProductionOrchestratorStatus(str, Enum):
    BLOCKED_BY_QUALITY_OR_DELIVERY = "BLOCKED_BY_QUALITY_OR_DELIVERY"
    READY_FOR_VIDEO_BASE = "READY_FOR_VIDEO_BASE"
    WAITING_FOR_HUMAN_REVIEW = "WAITING_FOR_HUMAN_REVIEW"
    HUMAN_REVIEW_REJECTED = "HUMAN_REVIEW_REJECTED"
    READY_FOR_FINALIZATION = "READY_FOR_FINALIZATION"
    READY_FOR_PUBLICATION_PACKAGE = "READY_FOR_PUBLICATION_PACKAGE"
    COMPLETE = "COMPLETE"


_DOWNSTREAM_ONLY_STATUSES = {
    ProductionOrchestratorStatus.READY_FOR_FINALIZATION,
    ProductionOrchestratorStatus.READY_FOR_PUBLICATION_PACKAGE,
    ProductionOrchestratorStatus.COMPLETE,
}


class ProductionOrchestratorRequest(StrictProductionOrchestratorModel):
    quality_gates: QualityGatesPlan
    delivery: DeliveryRenderPlan
    video_base_manifest: VideoBaseRenderManifest | None = None

    # Legacy input surface retained only so unsafe callers fail explicitly rather
    # than being silently interpreted. Human approval is authoritative in
    # FinalizationE2E, downstream of VideoBaseE2E.
    human_review_state: HumanReviewState = HumanReviewState.PENDING
    finalization_complete: bool = False
    publication_package_complete: bool = False

    @model_validator(mode="after")
    def validate_request(self):
        if self.delivery.source_quality_gates_hash != self.quality_gates.quality_gates_hash:
            raise ValueError("F29/F30 quality hash mismatch")
        if self.delivery.source_plan_context_hash != self.quality_gates.source_plan_context_hash:
            raise ValueError("F29/F30 context mismatch")

        if self.human_review_state == HumanReviewState.APPROVED:
            raise ValueError(
                "declarative APPROVED is not authoritative; use FinalizationE2E "
                "with HumanFinalReviewRecord and all required review gates"
            )
        if self.finalization_complete:
            raise ValueError(
                "finalization_complete is downstream evidence and cannot be "
                "declared in ProductionOrchestrator"
            )
        if self.publication_package_complete:
            raise ValueError(
                "publication_package_complete is downstream evidence and cannot "
                "be declared in ProductionOrchestrator"
            )
        return self


class ProductionOrchestratorPlan(StrictProductionOrchestratorModel):
    version: str = PRODUCTION_ORCHESTRATOR_VERSION
    subject: str
    source_plan_context_hash: str
    source_quality_gates_hash: str
    source_delivery_render_hash: str

    deterministic: bool = True
    orchestration_only: bool = True
    resource_class: str = "LIGHT"
    invokes_render: bool = False
    invokes_llm: bool = False
    invokes_network: bool = False
    writes_runtime_config: bool = False
    auto_publication: bool = False
    authorization_to_publish: bool = False
    uploads_files: bool = False
    webhook_calls: int = 0
    marks_published: bool = False

    status: ProductionOrchestratorStatus
    next_action: str
    quality_ready: bool
    delivery_ready: bool
    video_base_present: bool
    human_review_state: HumanReviewState
    finalization_complete: bool = False
    publication_package_complete: bool = False

    production_orchestrator_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if (
            not self.orchestration_only
            or self.invokes_render
            or self.invokes_llm
            or self.invokes_network
            or self.writes_runtime_config
            or self.auto_publication
            or self.authorization_to_publish
            or self.uploads_files
            or self.webhook_calls
            or self.marks_published
        ):
            raise ValueError("F51/C3 publication safety guardrail violation")

        if self.human_review_state == HumanReviewState.APPROVED:
            raise ValueError(
                "ProductionOrchestrator cannot certify human approval"
            )
        if self.finalization_complete or self.publication_package_complete:
            raise ValueError(
                "ProductionOrchestrator cannot certify downstream completion"
            )
        if self.status in _DOWNSTREAM_ONLY_STATUSES:
            raise ValueError(
                "downstream state requires FinalizationE2E/PublicationPackage authority"
            )
        return self
