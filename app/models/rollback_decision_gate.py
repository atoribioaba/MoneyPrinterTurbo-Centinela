from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.canary_monitor import CanaryMonitorPlan
from app.models.policy_registry import PolicyRegistryPlan


ROLLBACK_DECISION_GATE_VERSION = "rollback-decision-gate-v0.1"


class StrictRollbackGateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RollbackGateStatus(str, Enum):
    WAITING_FOR_MONITORING_EVIDENCE = "WAITING_FOR_MONITORING_EVIDENCE"
    DECISIONS_READY = "DECISIONS_READY"


class RollbackDecision(str, Enum):
    ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"
    ELIGIBLE_FOR_PROMOTION_REVIEW = "ELIGIBLE_FOR_PROMOTION_REVIEW"


class RollbackDecisionRequest(StrictRollbackGateModel):
    registry: PolicyRegistryPlan
    monitor: CanaryMonitorPlan


class PolicyRollbackDecision(StrictRollbackGateModel):
    policy_version: str
    decision: RollbackDecision
    breach_detected: bool

    rollback_target_policy_version: str | None = None
    rollback_to_baseline_default: bool = False
    baseline_parameter: str
    baseline_value: bool | float

    deterministic_decision: bool = True
    requires_human_execution: bool = True
    rollback_executed: bool = False
    promotion_executed: bool = False


class RollbackDecisionPlan(StrictRollbackGateModel):
    version: str = ROLLBACK_DECISION_GATE_VERSION
    source_policy_registry_hash: str
    source_canary_monitor_hash: str

    deterministic: bool = True
    resource_class: str = "LIGHT"

    decision_automatic: bool = True
    executes_rollback: bool = False
    writes_runtime_config: bool = False
    activates_policy: bool = False
    promotes_policy: bool = False
    uses_llm: bool = False
    network_calls: int = 0
    auto_publication: bool = False

    status: RollbackGateStatus
    decision_count: int = Field(ge=0)
    rollback_required_count: int = Field(ge=0)
    promotion_review_count: int = Field(ge=0)
    decisions: list[PolicyRollbackDecision]

    rollback_decision_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.decision_count != len(self.decisions):
            raise ValueError("decision_count mismatch")
        if self.rollback_required_count != sum(
            item.decision == RollbackDecision.ROLLBACK_REQUIRED for item in self.decisions
        ):
            raise ValueError("rollback_required_count mismatch")
        if self.promotion_review_count != sum(
            item.decision == RollbackDecision.ELIGIBLE_FOR_PROMOTION_REVIEW
            for item in self.decisions
        ):
            raise ValueError("promotion_review_count mismatch")

        expected = (
            RollbackGateStatus.DECISIONS_READY
            if self.decisions
            else RollbackGateStatus.WAITING_FOR_MONITORING_EVIDENCE
        )
        if self.status != expected:
            raise ValueError("status mismatch")

        if (
            not self.decision_automatic
            or self.executes_rollback
            or self.writes_runtime_config
            or self.activates_policy
            or self.promotes_policy
            or self.uses_llm
            or self.network_calls != 0
            or self.auto_publication
        ):
            raise ValueError("F49 guardrail violation")
        return self
