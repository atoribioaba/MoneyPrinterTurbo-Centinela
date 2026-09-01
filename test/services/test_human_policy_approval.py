from datetime import datetime,timezone
import pytest
from app.models.human_policy_approval import HumanDecision,HumanPolicyApprovalRequest,HumanPolicyApprovalStatus,PolicyHumanDecision
from app.models.policy_comparator import PolicyComparatorPlan,PolicyComparatorStatus,PolicyComparison
from app.services.human_policy_approval import build_human_policy_approval
NOW=datetime(2026,8,22,tzinfo=timezone.utc)
def comp(safe=True):
    x=PolicyComparison(policy_candidate_id="p1",simulation_count=1,behavior_change_count=1,structural_regression_count=0 if safe else 1,placeholder_regression_count=0,safe_for_human_review=safe)
    return PolicyComparatorPlan(source_policy_simulator_hash="sim",status=PolicyComparatorStatus.SAFE_CANDIDATES_READY if safe else PolicyComparatorStatus.NO_SAFE_CANDIDATES,candidate_count=1,safe_candidate_count=1 if safe else 0,comparisons=[x],policy_comparator_hash="cmp",generated_at_utc=NOW)
def dec(kind=HumanDecision.APPROVE): return PolicyHumanDecision(policy_candidate_id="p1",decision=kind,reviewer_ref="human",rationale="Reviewed simulation evidence.",decided_at_utc=NOW)
def test_waits(): assert build_human_policy_approval(HumanPolicyApprovalRequest(comparator=comp())).status==HumanPolicyApprovalStatus.WAITING_FOR_HUMAN_DECISIONS
def test_approval_recorded(): assert build_human_policy_approval(HumanPolicyApprovalRequest(comparator=comp(),decisions=[dec()])).approved_count==1
def test_rejection_recorded(): assert build_human_policy_approval(HumanPolicyApprovalRequest(comparator=comp(),decisions=[dec(HumanDecision.REJECT)])).rejected_count==1
def test_unsafe_rejected():
    with pytest.raises(RuntimeError):
        build_human_policy_approval(HumanPolicyApprovalRequest(comparator=comp(False),decisions=[dec()]))
def test_does_not_activate():
    r=build_human_policy_approval(HumanPolicyApprovalRequest(comparator=comp(),decisions=[dec()]))
    assert not r.auto_approval and not r.activates_policy and not r.edits_project
