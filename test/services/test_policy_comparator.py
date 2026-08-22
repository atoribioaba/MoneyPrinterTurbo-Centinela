from datetime import datetime,timezone
from app.models.policy_comparator import PolicyComparatorRequest,PolicyComparatorStatus
from app.models.policy_simulator import PolicySimulationResult,PolicySimulatorPlan,PolicySimulatorStatus
from app.services.policy_comparator import build_policy_comparator
NOW=datetime(2026,8,22,tzinfo=timezone.utc)
def row(ok=True,ph=True): return PolicySimulationResult(policy_candidate_id="p1",case_id="c1",parameter="intensity_bias",baseline_direction_hash="a",candidate_direction_hash="b",behavior_changed=True,baseline_tension_curve=[.2,.9],candidate_tension_curve=[.25,.95],baseline_climax_scene=2,candidate_climax_scene=2,baseline_structural_checks_pass=True,candidate_structural_checks_pass=ok,placeholders_preserved=ph)
def sim(rows): return PolicySimulatorPlan(source_policy_candidate_hash="c",status=PolicySimulatorStatus.SIMULATIONS_READY if rows else PolicySimulatorStatus.WAITING_FOR_CANDIDATE_POLICY_AND_CASES,case_count=len(rows),simulation_count=len(rows),behavior_change_count=sum(x.behavior_changed for x in rows),results=rows,policy_simulator_hash="sim",generated_at_utc=NOW)
def test_empty_waits(): assert build_policy_comparator(PolicyComparatorRequest(simulations=sim([]))).status==PolicyComparatorStatus.WAITING_FOR_SIMULATIONS
def test_safe_ready(): assert build_policy_comparator(PolicyComparatorRequest(simulations=sim([row()]))).safe_candidate_count==1
def test_regression_blocks(): assert build_policy_comparator(PolicyComparatorRequest(simulations=sim([row(False)]))).status==PolicyComparatorStatus.NO_SAFE_CANDIDATES
def test_no_quality_claim():
    r=build_policy_comparator(PolicyComparatorRequest(simulations=sim([row()]))); assert not r.quality_improvement_claims and not r.causal_claims
