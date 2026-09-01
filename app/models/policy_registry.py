from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Annotated
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictFloat,model_validator
from app.models.human_policy_approval import HumanPolicyApprovalPlan
from app.models.policy_candidate import PolicyCandidatePlan,PolicyTargetComponent
POLICY_REGISTRY_VERSION="policy-registry-v0.1"
PolicyScalar=Annotated[StrictBool|StrictFloat,Field(union_mode="left_to_right")]
class StrictPolicyRegistryModel(BaseModel):
    model_config=ConfigDict(extra="forbid",validate_assignment=True)
class PolicyRegistryStatus(str,Enum):
    WAITING_FOR_APPROVED_POLICY="WAITING_FOR_APPROVED_POLICY"
    VERSIONED_POLICIES_REGISTERED="VERSIONED_POLICIES_REGISTERED"
class PreviousPolicyReference(StrictPolicyRegistryModel):
    target_component:PolicyTargetComponent
    parameter:str
    policy_version:str=Field(min_length=1,max_length=128)
class PolicyRegistryRequest(StrictPolicyRegistryModel):
    candidates:PolicyCandidatePlan
    approvals:HumanPolicyApprovalPlan
    previous_versions:list[PreviousPolicyReference]=Field(default_factory=list)
class PolicyRegistryEntry(StrictPolicyRegistryModel):
    policy_version:str
    policy_candidate_id:str
    approval_record_hash:str
    target_component:PolicyTargetComponent
    parameter:str
    baseline_value:PolicyScalar
    candidate_value:PolicyScalar
    previous_policy_version:str|None=None
    rollback_target_policy_version:str|None=None
    immutable_entry:bool=True
    eligible_for_shadow_evaluation:bool=True
    active:bool=False
    @model_validator(mode="after")
    def valid(self):
        if not self.immutable_entry or not self.eligible_for_shadow_evaluation or self.active or self.rollback_target_policy_version!=self.previous_policy_version:
            raise ValueError("F45 entry guardrail violation")
        return self
class PolicyRegistryPlan(StrictPolicyRegistryModel):
    version:str=POLICY_REGISTRY_VERSION
    source_policy_candidate_hash:str
    source_human_policy_approval_hash:str
    deterministic:bool=True
    planning_only:bool=True
    resource_class:str="LIGHT"
    immutable_registry:bool=True
    writes_runtime_config:bool=False
    database_writes:int=0
    activates_policy:bool=False
    active_policy_changed:bool=False
    rollback_metadata_generated:bool
    uses_llm:bool=False
    network_calls:int=0
    auto_publication:bool=False
    status:PolicyRegistryStatus
    entry_count:int=Field(ge=0)
    entries:list[PolicyRegistryEntry]
    policy_registry_hash:str
    generated_at_utc:datetime
    @model_validator(mode="after")
    def valid(self):
        if self.entry_count!=len(self.entries) or self.rollback_metadata_generated!=bool(self.entries):
            raise ValueError("registry count mismatch")
        exp=PolicyRegistryStatus.VERSIONED_POLICIES_REGISTERED if self.entries else PolicyRegistryStatus.WAITING_FOR_APPROVED_POLICY
        if self.status!=exp:
            raise ValueError("status mismatch")
        if not self.planning_only or not self.immutable_registry or self.writes_runtime_config or self.database_writes or self.activates_policy or self.active_policy_changed or self.uses_llm or self.network_calls or self.auto_publication:
            raise ValueError("F45 guardrail violation")
        return self
