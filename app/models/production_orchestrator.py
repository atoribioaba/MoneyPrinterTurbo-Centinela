from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.delivery_render import DeliveryRenderPlan, DeliveryRenderStatus
from app.models.quality_gates import QualityGatesPlan
from app.models.video_base import VideoBaseRenderManifest

PRODUCTION_ORCHESTRATOR_VERSION = "production-orchestrator-v0.1"


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


class ProductionOrchestratorRequest(StrictProductionOrchestratorModel):
    quality_gates: QualityGatesPlan
    delivery: DeliveryRenderPlan
    video_base_manifest: VideoBaseRenderManifest | None = None
    human_review_state: HumanReviewState = HumanReviewState.PENDING
    finalization_complete: bool = False
    publication_package_complete: bool = False

    @model_validator(mode="after")
    def validate_request(self):
        if self.delivery.source_quality_gates_hash != self.quality_gates.quality_gates_hash:
            raise ValueError("F29/F30 quality hash mismatch")
        if self.delivery.source_plan_context_hash != self.quality_gates.source_plan_context_hash:
            raise ValueError("F29/F30 context mismatch")
        if self.finalization_complete and self.human_review_state != HumanReviewState.APPROVED:
            raise ValueError("finalization requires explicit approved human review")
        if self.publication_package_complete and not self.finalization_complete:
            raise ValueError("publication package cannot precede finalization")
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

    status: ProductionOrchestratorStatus
    next_action: str
    quality_ready: bool
    delivery_ready: bool
    video_base_present: bool
    human_review_state: HumanReviewState
    finalization_complete: bool
    publication_package_complete: bool

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
        ):
            raise ValueError("F51 guardrail violation")
        if self.publication_package_complete and not self.finalization_complete:
            raise ValueError("publication package state invalid")
        return self
