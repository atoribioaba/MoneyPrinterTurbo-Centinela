from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel,ConfigDict,Field,model_validator
from app.models.policy_comparator import PolicyComparatorPlan
HUMAN_POLICY_APPROVAL_VERSION="human-policy-approval-v0.1"
class StrictHumanPolicyApprovalModel(BaseModel): model_config=ConfigDict(extra="forbid",validate_assignment=True)
class HumanDecision(str,Enum): APPROVE="APPROVE"; REJECT="REJECT"
class HumanPolicyApprovalStatus(str,Enum): WAITING_FOR_HUMAN_DECISIONS="WAITING_FOR_HUMAN_DECISIONS"; HUMAN_DECISIONS_RECORDED="HUMAN_DECISIONS_RECORDED"
class PolicyHumanDecision(StrictHumanPolicyApprovalModel): policy_candidate_id:str=Field(min_length=1,max_length=128); decision:HumanDecision; reviewer_ref:str=Field(min_length=1,max_length=128); rationale:str=Field(min_length=1,max_length=1500); decided_at_utc:datetime
class HumanPolicyApprovalRequest(StrictHumanPolicyApprovalModel): comparator:PolicyComparatorPlan; decisions:list[PolicyHumanDecision]=Field(default_factory=list)
class PolicyApprovalRecord(StrictHumanPolicyApprovalModel): policy_candidate_id:str; decision:HumanDecision; reviewer_ref:str; rationale:str; decided_at_utc:datetime; comparator_safe_for_review:bool; approval_record_hash:str
class HumanPolicyApprovalPlan(StrictHumanPolicyApprovalModel):
    version:str=HUMAN_POLICY_APPROVAL_VERSION; source_policy_comparator_hash:str; deterministic:bool=True; planning_only:bool=True; resource_class:str="LIGHT"; auto_approval:bool=False; activates_policy:bool=False; edits_project:bool=False; uses_llm:bool=False; network_calls:int=0; auto_publication:bool=False
    status:HumanPolicyApprovalStatus; safe_candidate_count:int=Field(ge=0); decision_count:int=Field(ge=0); approved_count:int=Field(ge=0); rejected_count:int=Field(ge=0); pending_count:int=Field(ge=0); records:list[PolicyApprovalRecord]; human_policy_approval_hash:str; generated_at_utc:datetime
    @model_validator(mode="after")
    def valid(self):
        if self.decision_count!=len(self.records) or self.approved_count!=sum(x.decision==HumanDecision.APPROVE for x in self.records) or self.rejected_count!=sum(x.decision==HumanDecision.REJECT for x in self.records) or self.pending_count!=self.safe_candidate_count-self.decision_count: raise ValueError("approval count mismatch")
        if not self.planning_only or self.auto_approval or self.activates_policy or self.edits_project or self.uses_llm or self.network_calls or self.auto_publication: raise ValueError("F44 guardrail violation")
        return self
