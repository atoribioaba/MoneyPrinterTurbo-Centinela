from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, model_validator

from app.models.shadow_policy_evaluator import ShadowPolicyPlan


CANARY_POLICY_PLANNER_VERSION = "canary-policy-planner-v0.1"


class StrictCanaryPolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CanaryPolicyStatus(str, Enum):
    WAITING_FOR_SHADOW_EVIDENCE = "WAITING_FOR_SHADOW_EVIDENCE"
    NO_CANARY_ELIGIBLE = "NO_CANARY_ELIGIBLE"
    CANARY_PLANS_READY = "CANARY_PLANS_READY"


class CanaryPolicyRequest(StrictCanaryPolicyModel):
    shadow: ShadowPolicyPlan
    requested_exposure_fraction: StrictFloat = Field(default=0.05, ge=0.01, le=0.10)


class CanaryPolicyCandidate(StrictCanaryPolicyModel):
    policy_version: str
    policy_candidate_id: str
    parameter: str
    requested_exposure_fraction: float = Field(ge=0.01, le=0.10)
    shadow_case_count: int = Field(ge=1)
    shadow_safe_count: int = Field(ge=1)
    shadow_behavior_change_count: int = Field(ge=1)

    requires_human_launch: bool = True
    launched: bool = False
    writes_runtime_config: bool = False
    activates_policy: bool = False


class CanaryPolicyPlan(StrictCanaryPolicyModel):
    version: str = CANARY_POLICY_PLANNER_VERSION
    source_shadow_policy_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    max_exposure_fraction: float = 0.10
    executes_canary: bool = False
    writes_runtime_config: bool = False
    activates_policy: bool = False
    auto_rollback: bool = False
    uses_llm: bool = False
    network_calls: int = 0
    auto_publication: bool = False

    status: CanaryPolicyStatus
    evaluated_policy_count: int = Field(ge=0)
    canary_candidate_count: int = Field(ge=0)
    candidates: list[CanaryPolicyCandidate]

    canary_policy_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.canary_candidate_count != len(self.candidates):
            raise ValueError("canary_candidate_count mismatch")
        if any(item.requested_exposure_fraction > self.max_exposure_fraction for item in self.candidates):
            raise ValueError("canary exposure exceeds max")

        if (
            not self.planning_only
            or self.max_exposure_fraction != 0.10
            or self.executes_canary
            or self.writes_runtime_config
            or self.activates_policy
            or self.auto_rollback
            or self.uses_llm
            or self.network_calls != 0
            or self.auto_publication
        ):
            raise ValueError("F47 guardrail violation")
        return self
