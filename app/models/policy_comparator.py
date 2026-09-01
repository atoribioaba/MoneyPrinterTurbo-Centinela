from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel,ConfigDict,Field,model_validator
from app.models.policy_simulator import PolicySimulatorPlan
POLICY_COMPARATOR_VERSION="policy-comparator-v0.1"
class StrictPolicyComparatorModel(BaseModel):
    model_config=ConfigDict(extra="forbid",validate_assignment=True)
class PolicyComparatorStatus(str,Enum):
    WAITING_FOR_SIMULATIONS="WAITING_FOR_SIMULATIONS"
    NO_SAFE_CANDIDATES="NO_SAFE_CANDIDATES"
    SAFE_CANDIDATES_READY="SAFE_CANDIDATES_READY"
class PolicyComparatorRequest(StrictPolicyComparatorModel):
    simulations:PolicySimulatorPlan
class PolicyComparison(StrictPolicyComparatorModel):
    policy_candidate_id:str
    simulation_count:int=Field(ge=1)
    behavior_change_count:int=Field(ge=0)
    structural_regression_count:int=Field(ge=0)
    placeholder_regression_count:int=Field(ge=0)
    safe_for_human_review:bool
    quality_improvement_claimed:bool=False
    causal_claim:bool=False
    @model_validator(mode="after")
    def valid(self):
        if self.safe_for_human_review!=(self.structural_regression_count==0 and self.placeholder_regression_count==0):
            raise ValueError("safe mismatch")
        if self.quality_improvement_claimed or self.causal_claim:
            raise ValueError("F43 claim violation")
        return self
class PolicyComparatorPlan(StrictPolicyComparatorModel):
    version:str=POLICY_COMPARATOR_VERSION
    source_policy_simulator_hash:str
    deterministic:bool=True
    planning_only:bool=True
    resource_class:str="LIGHT"
    quality_improvement_claims:bool=False
    causal_claims:bool=False
    activates_policy:bool=False
    edits_project:bool=False
    uses_llm:bool=False
    network_calls:int=0
    auto_publication:bool=False
    status:PolicyComparatorStatus
    candidate_count:int=Field(ge=0)
    safe_candidate_count:int=Field(ge=0)
    comparisons:list[PolicyComparison]
    policy_comparator_hash:str
    generated_at_utc:datetime
    @model_validator(mode="after")
    def valid(self):
        if self.candidate_count!=len(self.comparisons) or self.safe_candidate_count!=sum(x.safe_for_human_review for x in self.comparisons):
            raise ValueError("count mismatch")
        if not self.planning_only or self.quality_improvement_claims or self.causal_claims or self.activates_policy or self.edits_project or self.uses_llm or self.network_calls or self.auto_publication:
            raise ValueError("F43 guardrail violation")
        return self
