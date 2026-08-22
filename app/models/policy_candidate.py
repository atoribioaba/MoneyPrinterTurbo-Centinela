from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, model_validator
from app.models.evidence_recommendation_gate import EvidenceRecommendationGatePlan
POLICY_CANDIDATE_VERSION = "policy-candidate-v0.1"
PolicyScalar = Annotated[StrictBool | StrictFloat, Field(union_mode="left_to_right")]
class StrictPolicyCandidateModel(BaseModel): model_config = ConfigDict(extra="forbid", validate_assignment=True)
class PolicyCandidateStatus(str, Enum):
    WAITING_FOR_EXPLICIT_POLICY_BINDINGS="WAITING_FOR_EXPLICIT_POLICY_BINDINGS"
    CANDIDATE_POLICIES_READY="CANDIDATE_POLICIES_READY"
class PolicyTargetComponent(str, Enum): CINEMATIC_DIRECTOR_REQUEST="CINEMATIC_DIRECTOR_REQUEST"
class PolicyBinding(StrictPolicyCandidateModel):
    recommendation_id:str=Field(min_length=1,max_length=128); target_component:PolicyTargetComponent=PolicyTargetComponent.CINEMATIC_DIRECTOR_REQUEST
    parameter:str=Field(min_length=1,max_length=128); baseline_value:PolicyScalar; candidate_value:PolicyScalar; human_mapping_confirmed:bool=False
class PolicyCandidateRequest(StrictPolicyCandidateModel): recommendations:EvidenceRecommendationGatePlan; bindings:list[PolicyBinding]=Field(default_factory=list)
class CandidatePolicy(StrictPolicyCandidateModel):
    policy_candidate_id:str; recommendation_id:str; experiment_id:str; hypothesis_id:str; evidence_class:str; target_component:PolicyTargetComponent
    parameter:str; baseline_value:PolicyScalar; candidate_value:PolicyScalar; human_mapping_confirmed:bool=True; requires_simulation:bool=True; approved_for_activation:bool=False
    @model_validator(mode="after")
    def valid(self):
        if not self.human_mapping_confirmed or not self.requires_simulation or self.approved_for_activation: raise ValueError("F41 candidate guardrail violation")
        return self
class PolicyCandidatePlan(StrictPolicyCandidateModel):
    version:str=POLICY_CANDIDATE_VERSION; source_recommendation_gate_hash:str; deterministic:bool=True; planning_only:bool=True; resource_class:str="LIGHT"
    inferred_bindings:bool=False; edits_project:bool=False; updates_director_policy:bool=False; activates_policy:bool=False; uses_llm:bool=False; network_calls:int=0; database_writes:int=0; auto_publication:bool=False
    status:PolicyCandidateStatus; binding_count:int=Field(ge=0); candidate_count:int=Field(ge=0); candidates:list[CandidatePolicy]; policy_candidate_hash:str; generated_at_utc:datetime
    @model_validator(mode="after")
    def valid(self):
        if self.candidate_count!=len(self.candidates): raise ValueError("candidate_count mismatch")
        expected=PolicyCandidateStatus.CANDIDATE_POLICIES_READY if self.candidates else PolicyCandidateStatus.WAITING_FOR_EXPLICIT_POLICY_BINDINGS
        if self.status!=expected: raise ValueError("status mismatch")
        if not self.planning_only or self.inferred_bindings or self.edits_project or self.updates_director_policy or self.activates_policy or self.uses_llm or self.network_calls or self.database_writes or self.auto_publication: raise ValueError("F41 guardrail violation")
        return self
