from __future__ import annotations
import hashlib
import json
from collections import defaultdict
from datetime import datetime,timezone
from app.models.policy_comparator import POLICY_COMPARATOR_VERSION,PolicyComparatorPlan,PolicyComparatorRequest,PolicyComparatorStatus,PolicyComparison
def _hash(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest().upper()
def build_policy_comparator(request:PolicyComparatorRequest)->PolicyComparatorPlan:
    g=defaultdict(list)
    for r in request.simulations.results:
        g[r.policy_candidate_id].append(r)
    out=[]
    for cid in sorted(g):
        rows=g[cid]
        sr=sum((not x.candidate_structural_checks_pass) or (not x.baseline_structural_checks_pass) for x in rows)
        pr=sum(not x.placeholders_preserved for x in rows)
        out.append(PolicyComparison(policy_candidate_id=cid,simulation_count=len(rows),behavior_change_count=sum(x.behavior_changed for x in rows),structural_regression_count=sr,placeholder_regression_count=pr,safe_for_human_review=(sr==0 and pr==0)))
    safe=sum(x.safe_for_human_review for x in out)
    status=PolicyComparatorStatus.WAITING_FOR_SIMULATIONS if not out else (PolicyComparatorStatus.SAFE_CANDIDATES_READY if safe else PolicyComparatorStatus.NO_SAFE_CANDIDATES)
    stable={"version":POLICY_COMPARATOR_VERSION,"sim":request.simulations.policy_simulator_hash,"comparisons":[x.model_dump(mode="json") for x in out]}
    return PolicyComparatorPlan(source_policy_simulator_hash=request.simulations.policy_simulator_hash,status=status,candidate_count=len(out),safe_candidate_count=safe,comparisons=out,policy_comparator_hash=_hash(stable),generated_at_utc=datetime.now(timezone.utc))
