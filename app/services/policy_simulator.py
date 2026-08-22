from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from app.models.cinematic_director import CinematicDirectorRequest
from app.models.policy_candidate import PolicyTargetComponent
from app.models.policy_simulator import POLICY_SIMULATOR_VERSION,PolicySimulationResult,PolicySimulatorPlan,PolicySimulatorRequest,PolicySimulatorStatus
from app.services.cinematic_director import CinematicDirector
class PolicySimulatorError(RuntimeError): pass
SUPPORTED_PARAMETERS={"intensity_bias":("float",-0.20,0.20),"prefer_observation_over_motion":("bool",None,None),"preserve_source_transition_intent":("bool",None,None)}
def _validate_candidate(candidate):
    spec=SUPPORTED_PARAMETERS.get(candidate.parameter)
    if spec is None: raise PolicySimulatorError(f"unsupported policy parameter: {candidate.parameter}")
    kind,lo,hi=spec; value=candidate.candidate_value
    if kind=="bool" and type(value) is not bool: raise PolicySimulatorError(f"{candidate.parameter} requires boolean candidate value")
    if kind=="float":
        if type(value) is bool or not isinstance(value,float): raise PolicySimulatorError(f"{candidate.parameter} requires float candidate value")
        if not lo<=value<=hi: raise PolicySimulatorError(f"{candidate.parameter} outside allowed range [{lo}, {hi}]")
def _hash(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest().upper()
def _checks(d):
    c=d.structural_checks; return all((c.act_order_valid,c.climax_present,c.epilogue_present,c.scene_number_alignment,c.duration_alignment,c.placeholders_preserved))
def build_policy_simulator(request:PolicySimulatorRequest)->PolicySimulatorPlan:
    director=CinematicDirector(); out=[]
    for candidate in request.candidates.candidates:
        if candidate.target_component!=PolicyTargetComponent.CINEMATIC_DIRECTOR_REQUEST: raise PolicySimulatorError("unsupported target component")
        _validate_candidate(candidate)
        for case in request.cases:
            base_req=CinematicDirectorRequest(plan=case.plan,video_base=case.video_base)
            actual=getattr(base_req,candidate.parameter)
            if actual!=candidate.baseline_value: raise PolicySimulatorError(f"baseline mismatch for {candidate.parameter}: request={actual!r} candidate={candidate.baseline_value!r}")
            candidate_payload=base_req.model_dump(mode="python")
            candidate_payload[candidate.parameter]=candidate.candidate_value
            cand_req=CinematicDirectorRequest.model_validate(candidate_payload)
            base=director.build(base_req); cand=director.build(cand_req)
            out.append(PolicySimulationResult(policy_candidate_id=candidate.policy_candidate_id,case_id=case.case_id,parameter=candidate.parameter,baseline_direction_hash=base.direction_hash,candidate_direction_hash=cand.direction_hash,behavior_changed=base.direction_hash!=cand.direction_hash,baseline_tension_curve=base.tension_curve,candidate_tension_curve=cand.tension_curve,baseline_climax_scene=base.climax_scene_number,candidate_climax_scene=cand.climax_scene_number,baseline_structural_checks_pass=_checks(base),candidate_structural_checks_pass=_checks(cand),placeholders_preserved=(base.placeholder_count==cand.placeholder_count and all(a.placeholder==b.placeholder for a,b in zip(base.scenes,cand.scenes)))))
    out.sort(key=lambda x:(x.policy_candidate_id,x.case_id)); stable={"version":POLICY_SIMULATOR_VERSION,"candidate_hash":request.candidates.policy_candidate_hash,"results":[x.model_dump(mode="json") for x in out]}
    return PolicySimulatorPlan(source_policy_candidate_hash=request.candidates.policy_candidate_hash,status=PolicySimulatorStatus.SIMULATIONS_READY if out else PolicySimulatorStatus.WAITING_FOR_CANDIDATE_POLICY_AND_CASES,case_count=len(request.cases),simulation_count=len(out),behavior_change_count=sum(x.behavior_changed for x in out),results=out,policy_simulator_hash=_hash(stable),generated_at_utc=datetime.now(timezone.utc))
