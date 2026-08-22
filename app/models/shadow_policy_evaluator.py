from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.policy_registry import PolicyRegistryPlan
from app.models.policy_simulator import PolicySimulationCase


SHADOW_POLICY_EVALUATOR_VERSION = "shadow-policy-evaluator-v0.1"


class StrictShadowPolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ShadowPolicyStatus(str, Enum):
    WAITING_FOR_REGISTERED_POLICY_AND_CASES = "WAITING_FOR_REGISTERED_POLICY_AND_CASES"
    SHADOW_RESULTS_READY = "SHADOW_RESULTS_READY"


class ShadowPolicyRequest(StrictShadowPolicyModel):
    registry: PolicyRegistryPlan
    cases: list[PolicySimulationCase] = Field(default_factory=list)


class ShadowPolicyResult(StrictShadowPolicyModel):
    policy_version: str
    policy_candidate_id: str
    case_id: str
    parameter: str

    baseline_direction_hash: str
    candidate_direction_hash: str
    behavior_changed: bool

    baseline_structural_checks_pass: bool
    candidate_structural_checks_pass: bool
    placeholders_preserved: bool
    structural_safe: bool

    runtime_effect: bool = False
    writes_runtime_config: bool = False
    renders_video: bool = False
    publishes: bool = False


class ShadowPolicyPlan(StrictShadowPolicyModel):
    version: str = SHADOW_POLICY_EVALUATOR_VERSION
    source_policy_registry_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    uses_real_cinematic_director: bool = True
    shadow_only: bool = True
    runtime_effect: bool = False
    writes_runtime_config: bool = False
    activates_policy: bool = False
    renders_video: bool = False
    gpu_required: bool = False
    uses_llm: bool = False
    network_calls: int = 0
    auto_publication: bool = False

    status: ShadowPolicyStatus
    registered_policy_count: int = Field(ge=0)
    case_count: int = Field(ge=0)
    evaluation_count: int = Field(ge=0)
    safe_evaluation_count: int = Field(ge=0)
    behavior_change_count: int = Field(ge=0)
    results: list[ShadowPolicyResult]

    shadow_policy_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.evaluation_count != len(self.results):
            raise ValueError("evaluation_count mismatch")
        if self.safe_evaluation_count != sum(item.structural_safe for item in self.results):
            raise ValueError("safe_evaluation_count mismatch")
        if self.behavior_change_count != sum(item.behavior_changed for item in self.results):
            raise ValueError("behavior_change_count mismatch")

        expected = (
            ShadowPolicyStatus.SHADOW_RESULTS_READY
            if self.results
            else ShadowPolicyStatus.WAITING_FOR_REGISTERED_POLICY_AND_CASES
        )
        if self.status != expected:
            raise ValueError("status mismatch")

        if (
            not self.planning_only
            or not self.uses_real_cinematic_director
            or not self.shadow_only
            or self.runtime_effect
            or self.writes_runtime_config
            or self.activates_policy
            or self.renders_video
            or self.gpu_required
            or self.uses_llm
            or self.network_calls != 0
            or self.auto_publication
        ):
            raise ValueError("F46 guardrail violation")
        return self
