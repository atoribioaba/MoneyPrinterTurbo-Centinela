from __future__ import annotations
import hashlib
import json
from datetime import datetime,timezone
from app.models.policy_candidate import POLICY_CANDIDATE_VERSION,CandidatePolicy,PolicyCandidatePlan,PolicyCandidateRequest,PolicyCandidateStatus
class PolicyCandidateError(RuntimeError):
    pass
SUPPORTED={"intensity_bias":("float",-0.20,0.20),"prefer_observation_over_motion":("bool",None,None),"preserve_source_transition_intent":("bool",None,None)}
def _hash(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest().upper()
def _check(p,v):
    spec=SUPPORTED.get(p)
    if spec is None:
        raise PolicyCandidateError(f"unsupported policy parameter: {p}")
    kind,lo,hi=spec
    if kind=="bool" and type(v) is not bool:
        raise PolicyCandidateError(f"{p} requires boolean values")
    if kind=="float":
        if type(v) is bool or not isinstance(v,float):
            raise PolicyCandidateError(f"{p} requires strict float values")
        if not lo<=v<=hi:
            raise PolicyCandidateError(f"{p} outside allowed range [{lo}, {hi}]")
def build_policy_candidate(request:PolicyCandidateRequest)->PolicyCandidatePlan:
    recs={x.recommendation_id:x for x in request.recommendations.recommendations}
    seen=set()
    out=[]
    for b in request.bindings:
        if not b.human_mapping_confirmed:
            continue
        if b.recommendation_id in seen:
            raise PolicyCandidateError("duplicate recommendation binding")
        seen.add(b.recommendation_id)
        r=recs.get(b.recommendation_id)
        if r is None:
            raise PolicyCandidateError(f"unknown recommendation_id: {b.recommendation_id}")
        _check(b.parameter,b.baseline_value)
        _check(b.parameter,b.candidate_value)
        if b.baseline_value==b.candidate_value:
            raise PolicyCandidateError("baseline and candidate values must differ")
        stable={"rec":r.recommendation_id,"exp":r.experiment_id,"target":b.target_component.value,"parameter":b.parameter,"baseline":b.baseline_value,"candidate":b.candidate_value}
        out.append(CandidatePolicy(policy_candidate_id=_hash(stable),recommendation_id=r.recommendation_id,experiment_id=r.experiment_id,hypothesis_id=r.hypothesis_id,evidence_class=r.evidence_class,target_component=b.target_component,parameter=b.parameter,baseline_value=b.baseline_value,candidate_value=b.candidate_value))
    out.sort(key=lambda x:x.policy_candidate_id)
    stable={"version":POLICY_CANDIDATE_VERSION,"source":request.recommendations.evidence_recommendation_gate_hash,"candidates":[x.model_dump(mode="json") for x in out]}
    return PolicyCandidatePlan(source_recommendation_gate_hash=request.recommendations.evidence_recommendation_gate_hash,status=PolicyCandidateStatus.CANDIDATE_POLICIES_READY if out else PolicyCandidateStatus.WAITING_FOR_EXPLICIT_POLICY_BINDINGS,binding_count=len(request.bindings),candidate_count=len(out),candidates=out,policy_candidate_hash=_hash(stable),generated_at_utc=datetime.now(timezone.utc))
