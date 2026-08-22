from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from app.models.human_policy_approval import HumanDecision
from app.models.policy_registry import POLICY_REGISTRY_VERSION,PolicyRegistryEntry,PolicyRegistryPlan,PolicyRegistryRequest,PolicyRegistryStatus
class PolicyRegistryError(RuntimeError): pass
def _hash(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest().upper()
def build_policy_registry(request:PolicyRegistryRequest)->PolicyRegistryPlan:
    candidates={x.policy_candidate_id:x for x in request.candidates.candidates}; approvals={x.policy_candidate_id:x for x in request.approvals.records if x.decision==HumanDecision.APPROVE}; prev={}; seen=set(); out=[]
    for x in request.previous_versions:
        k=(x.target_component,x.parameter)
        if k in prev: raise PolicyRegistryError("duplicate previous policy reference")
        prev[k]=x.policy_version
    for cid in sorted(approvals):
        a=approvals[cid]; c=candidates.get(cid)
        if c is None: raise PolicyRegistryError("approved policy candidate not found")
        k=(c.target_component,c.parameter)
        if k in seen: raise PolicyRegistryError("multiple approved candidates target same parameter")
        seen.add(k); pv=prev.get(k); stable={"candidate":cid,"approval":a.approval_record_hash,"target":c.target_component.value,"parameter":c.parameter,"value":c.candidate_value,"previous":pv}
        out.append(PolicyRegistryEntry(policy_version=_hash(stable),policy_candidate_id=cid,approval_record_hash=a.approval_record_hash,target_component=c.target_component,parameter=c.parameter,baseline_value=c.baseline_value,candidate_value=c.candidate_value,previous_policy_version=pv,rollback_target_policy_version=pv))
    stable={"version":POLICY_REGISTRY_VERSION,"candidate_hash":request.candidates.policy_candidate_hash,"approval_hash":request.approvals.human_policy_approval_hash,"entries":[x.model_dump(mode="json") for x in out]}
    return PolicyRegistryPlan(source_policy_candidate_hash=request.candidates.policy_candidate_hash,source_human_policy_approval_hash=request.approvals.human_policy_approval_hash,rollback_metadata_generated=bool(out),status=PolicyRegistryStatus.VERSIONED_POLICIES_REGISTERED if out else PolicyRegistryStatus.WAITING_FOR_APPROVED_POLICY,entry_count=len(out),entries=out,policy_registry_hash=_hash(stable),generated_at_utc=datetime.now(timezone.utc))
