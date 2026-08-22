from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from app.models.human_policy_approval import HUMAN_POLICY_APPROVAL_VERSION,HumanDecision,HumanPolicyApprovalPlan,HumanPolicyApprovalRequest,HumanPolicyApprovalStatus,PolicyApprovalRecord
class HumanPolicyApprovalError(RuntimeError): pass
def _hash(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest().upper()
def build_human_policy_approval(request:HumanPolicyApprovalRequest)->HumanPolicyApprovalPlan:
    safe={x.policy_candidate_id:x for x in request.comparator.comparisons if x.safe_for_human_review}; seen=set(); records=[]
    for d in request.decisions:
        if d.policy_candidate_id in seen: raise HumanPolicyApprovalError("duplicate human decision")
        seen.add(d.policy_candidate_id)
        if d.policy_candidate_id not in safe: raise HumanPolicyApprovalError("human decision targets a candidate not safe for review")
        records.append(PolicyApprovalRecord(**d.model_dump(),comparator_safe_for_review=True,approval_record_hash=_hash(d.model_dump(mode="json"))))
    records.sort(key=lambda x:x.policy_candidate_id); stable={"version":HUMAN_POLICY_APPROVAL_VERSION,"comparator":request.comparator.policy_comparator_hash,"records":[x.model_dump(mode="json") for x in records]}
    return HumanPolicyApprovalPlan(source_policy_comparator_hash=request.comparator.policy_comparator_hash,status=HumanPolicyApprovalStatus.HUMAN_DECISIONS_RECORDED if records else HumanPolicyApprovalStatus.WAITING_FOR_HUMAN_DECISIONS,safe_candidate_count=len(safe),decision_count=len(records),approved_count=sum(x.decision==HumanDecision.APPROVE for x in records),rejected_count=sum(x.decision==HumanDecision.REJECT for x in records),pending_count=len(safe)-len(records),records=records,human_policy_approval_hash=_hash(stable),generated_at_utc=datetime.now(timezone.utc))
