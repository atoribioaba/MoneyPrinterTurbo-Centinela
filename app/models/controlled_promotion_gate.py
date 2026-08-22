from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.rollback_decision_gate import RollbackDecisionPlan


CONTROLLED_PROMOTION_GATE_VERSION = "controlled-promotion-gate-v0.1"


class StrictControlledPromotionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class PromotionDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class ControlledPromotionStatus(str, Enum):
    WAITING_FOR_PROMOTION_EVIDENCE = "WAITING_FOR_PROMOTION_EVIDENCE"
    PROMOTION_DECISIONS_RECORDED = "PROMOTION_DECISIONS_RECORDED"
    PROMOTION_AUTHORIZATIONS_READY = "PROMOTION_AUTHORIZATIONS_READY"


class HumanPromotionDecision(StrictControlledPromotionModel):
    policy_version: str = Field(min_length=1, max_length=128)
    decision: PromotionDecision
    reviewer_ref: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=1, max_length=1500)
    decided_at_utc: datetime


class ControlledPromotionRequest(StrictControlledPromotionModel):
    rollback_gate: RollbackDecisionPlan
    decisions: list[HumanPromotionDecision] = Field(default_factory=list)


class PromotionAuthorization(StrictControlledPromotionModel):
    policy_version: str
    decision: PromotionDecision
    reviewer_ref: str
    rationale: str
    decided_at_utc: datetime

    eligible_from_canary: bool = True
    authorized_for_future_activation: bool
    activation_executed: bool = False
    writes_runtime_config: bool = False
    auto_publication: bool = False

    promotion_record_hash: str


class ControlledPromotionPlan(StrictControlledPromotionModel):
    version: str = CONTROLLED_PROMOTION_GATE_VERSION
    source_rollback_decision_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    requires_human_promotion_decision: bool = True
    activates_policy: bool = False
    writes_runtime_config: bool = False
    auto_apply: bool = False
    executes_rollback: bool = False
    uses_llm: bool = False
    network_calls: int = 0
    auto_publication: bool = False

    status: ControlledPromotionStatus
    eligible_policy_count: int = Field(ge=0)
    decision_count: int = Field(ge=0)
    authorization_count: int = Field(ge=0)
    rejection_count: int = Field(ge=0)
    records: list[PromotionAuthorization]

    controlled_promotion_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.decision_count != len(self.records):
            raise ValueError("decision_count mismatch")
        if self.authorization_count != sum(
            item.authorized_for_future_activation for item in self.records
        ):
            raise ValueError("authorization_count mismatch")
        if self.rejection_count != sum(
            item.decision == PromotionDecision.REJECT for item in self.records
        ):
            raise ValueError("rejection_count mismatch")

        if (
            not self.planning_only
            or not self.requires_human_promotion_decision
            or self.activates_policy
            or self.writes_runtime_config
            or self.auto_apply
            or self.executes_rollback
            or self.uses_llm
            or self.network_calls != 0
            or self.auto_publication
        ):
            raise ValueError("F50 guardrail violation")
        return self
