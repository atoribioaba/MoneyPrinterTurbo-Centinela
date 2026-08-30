from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.delivery_render import DeliveryRenderPlan
from app.models.finalization_e2e import (
    FinalizationE2EPlan,
    FinalizationE2EStatus,
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.models.publication_package import (
    PublicationPackagePlan,
    PublicationPackageStatus,
)
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


class ProductionOrchestratorRequest(StrictProductionOrchestratorModel):
    quality_gates: QualityGatesPlan
    delivery: DeliveryRenderPlan
    video_base_manifest: VideoBaseRenderManifest | None = None
    human_review: HumanFinalReviewRecord | None = None
    finalization: FinalizationE2EPlan | None = None
    publication_package: PublicationPackagePlan | None = None

    @model_validator(mode="after")
    def validate_request(self):
        if self.delivery.source_quality_gates_hash != self.quality_gates.quality_gates_hash:
            raise ValueError("F29/F30 quality hash mismatch")
        if self.delivery.source_plan_context_hash != self.quality_gates.source_plan_context_hash:
            raise ValueError("F29/F30 context mismatch")

        if (
            self.human_review is not None
            and self.human_review.decision == HumanFinalReviewDecision.APPROVE
            and not self.human_review.all_required_gates_passed
        ):
            raise ValueError("approved human review requires all seven review gates")

        if self.finalization is not None:
            if self.human_review is None:
                raise ValueError("finalization evidence requires bound human review evidence")
            if self.finalization.status == FinalizationE2EStatus.FINALIZATION_E2E_PASS:
                if self.human_review.decision != HumanFinalReviewDecision.APPROVE:
                    raise ValueError("finalization pass requires approved human review")
                if not self.human_review.all_required_gates_passed:
                    raise ValueError("finalization pass requires all seven review gates")
                if not self.finalization.human_review_recorded:
                    raise ValueError("finalization pass requires recorded human review")

        if self.publication_package is not None:
            if self.finalization is None:
                raise ValueError("publication package evidence cannot precede finalization")
            if (
                self.publication_package.source_finalization_e2e_hash
                != self.finalization.finalization_e2e_hash
            ):
                raise ValueError("publication package/finalization evidence hash mismatch")
            if (
                self.publication_package.status
                == PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE
                and self.finalization.status
                != FinalizationE2EStatus.FINALIZATION_E2E_PASS
            ):
                raise ValueError("ready publication package requires certified finalization")
        return self


class ProductionOrchestratorPlan(StrictProductionOrchestratorModel):
    version: str = PRODUCTION_ORCHESTRATOR_VERSION
    subject: str
    source_plan_context_hash: str
    source_quality_gates_hash: str
    source_delivery_render_hash: str
    source_human_review_hash: str | None = None
    source_finalization_e2e_hash: str | None = None
    source_publication_package_hash: str | None = None

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
            or self.authorization_to_publish
            or self.uploads_files
            or self.webhook_calls
            or self.marks_published
        ):
            raise ValueError("F51/C3 publication safety guardrail violation")

        if self.finalization_complete:
            if self.human_review_state != HumanReviewState.APPROVED:
                raise ValueError("finalization completion requires approved human review")
            if not self.source_human_review_hash or not self.source_finalization_e2e_hash:
                raise ValueError("finalization completion requires bound evidence hashes")

        if self.publication_package_complete:
            if not self.finalization_complete:
                raise ValueError("publication package state invalid")
            if not self.source_publication_package_hash:
                raise ValueError("publication package completion requires bound evidence hash")

        if self.status == ProductionOrchestratorStatus.READY_FOR_FINALIZATION:
            if self.human_review_state != HumanReviewState.APPROVED:
                raise ValueError("READY_FOR_FINALIZATION requires approved human review")
            if not self.source_human_review_hash:
                raise ValueError("READY_FOR_FINALIZATION requires bound review evidence")

        if self.status == ProductionOrchestratorStatus.READY_FOR_PUBLICATION_PACKAGE:
            if not self.finalization_complete or not self.source_finalization_e2e_hash:
                raise ValueError("READY_FOR_PUBLICATION_PACKAGE requires certified finalization")

        if self.status == ProductionOrchestratorStatus.COMPLETE:
            if not self.publication_package_complete:
                raise ValueError("COMPLETE requires manual publication package readiness")
            if not self.source_publication_package_hash:
                raise ValueError("COMPLETE requires bound publication package evidence")
        return self
