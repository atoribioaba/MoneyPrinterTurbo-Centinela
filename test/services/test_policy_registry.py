from datetime import datetime,timezone
from app.models.human_policy_approval import HumanDecision,HumanPolicyApprovalPlan,HumanPolicyApprovalStatus,PolicyApprovalRecord
from app.models.policy_candidate import CandidatePolicy,PolicyCandidatePlan,PolicyCandidateStatus,PolicyTargetComponent
from app.models.policy_registry import PolicyRegistryRequest,PolicyRegistryStatus,PreviousPolicyReference
from app.services.policy_registry import build_policy_registry
NOW=datetime(2026,8,22,tzinfo=timezone.utc)
def cps():
    c=CandidatePolicy(policy_candidate_id="p1",recommendation_id="r1",experiment_id="e1",hypothesis_id="h1",evidence_class="CONTROLLED_EXPERIMENT_RESULT",target_component=PolicyTargetComponent.CINEMATIC_DIRECTOR_REQUEST,parameter="intensity_bias",baseline_value=0.0,candidate_value=0.05)
    return PolicyCandidatePlan(source_recommendation_gate_hash="g",status=PolicyCandidateStatus.CANDIDATE_POLICIES_READY,binding_count=1,candidate_count=1,candidates=[c],policy_candidate_hash="c",generated_at_utc=NOW)
def aps(ok=True):
    recs=[PolicyApprovalRecord(policy_candidate_id="p1",decision=HumanDecision.APPROVE,reviewer_ref="human",rationale="Approved for registry only.",decided_at_utc=NOW,comparator_safe_for_review=True,approval_record_hash="a")] if ok else []
    return HumanPolicyApprovalPlan(source_policy_comparator_hash="cmp",status=HumanPolicyApprovalStatus.HUMAN_DECISIONS_RECORDED if recs else HumanPolicyApprovalStatus.WAITING_FOR_HUMAN_DECISIONS,safe_candidate_count=1,decision_count=len(recs),approved_count=len(recs),rejected_count=0,pending_count=1-len(recs),records=recs,human_policy_approval_hash="h",generated_at_utc=NOW)
def test_waits_without_approval(): assert build_policy_registry(PolicyRegistryRequest(candidates=cps(),approvals=aps(False))).status==PolicyRegistryStatus.WAITING_FOR_APPROVED_POLICY
def test_versioned_not_active():
    r=build_policy_registry(PolicyRegistryRequest(candidates=cps(),approvals=aps()))
    assert r.entry_count==1 and not r.entries[0].active and not r.activates_policy
def test_rollback_reference():
    r=build_policy_registry(PolicyRegistryRequest(candidates=cps(),approvals=aps(),previous_versions=[PreviousPolicyReference(target_component=PolicyTargetComponent.CINEMATIC_DIRECTOR_REQUEST,parameter="intensity_bias",policy_version="v0")]))
    assert r.entries[0].rollback_target_policy_version=="v0"
def test_no_runtime_write():
    r=build_policy_registry(PolicyRegistryRequest(candidates=cps(),approvals=aps()))
    assert not r.writes_runtime_config and r.database_writes==0 and not r.active_policy_changed
