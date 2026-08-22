from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel,ConfigDict,Field,model_validator
from app.models.astronomy_director import AstronomyVideoPlan
from app.models.policy_candidate import PolicyCandidatePlan
from app.models.video_base import VideoBasePlan
POLICY_SIMULATOR_VERSION="policy-simulator-v0.1"
class StrictPolicySimulatorModel(BaseModel): model_config=ConfigDict(extra="forbid",validate_assignment=True)
class PolicySimulatorStatus(str,Enum):
    WAITING_FOR_CANDIDATE_POLICY_AND_CASES="WAITING_FOR_CANDIDATE_POLICY_AND_CASES"
    SIMULATIONS_READY="SIMULATIONS_READY"
class PolicySimulationCase(StrictPolicySimulatorModel): case_id:str=Field(min_length=1,max_length=128); plan:AstronomyVideoPlan; video_base:VideoBasePlan
class PolicySimulatorRequest(StrictPolicySimulatorModel): candidates:PolicyCandidatePlan; cases:list[PolicySimulationCase]=Field(default_factory=list)
class PolicySimulationResult(StrictPolicySimulatorModel):
    policy_candidate_id:str; case_id:str; parameter:str; baseline_direction_hash:str; candidate_direction_hash:str; behavior_changed:bool
    baseline_tension_curve:list[float]; candidate_tension_curve:list[float]; baseline_climax_scene:int; candidate_climax_scene:int
    baseline_structural_checks_pass:bool; candidate_structural_checks_pass:bool; placeholders_preserved:bool; renders_video:bool=False; gpu_required:bool=False; uses_llm:bool=False
class PolicySimulatorPlan(StrictPolicySimulatorModel):
    version:str=POLICY_SIMULATOR_VERSION; source_policy_candidate_hash:str; deterministic:bool=True; planning_only:bool=True; resource_class:str="LIGHT"
    uses_real_cinematic_director:bool=True; renders_video:bool=False; gpu_required:bool=False; uses_llm:bool=False; network_calls:int=0; writes_runtime_config:bool=False; activates_policy:bool=False; auto_publication:bool=False
    status:PolicySimulatorStatus; case_count:int=Field(ge=0); simulation_count:int=Field(ge=0); behavior_change_count:int=Field(ge=0); results:list[PolicySimulationResult]; policy_simulator_hash:str; generated_at_utc:datetime
    @model_validator(mode="after")
    def valid(self):
        if self.simulation_count!=len(self.results) or self.behavior_change_count!=sum(x.behavior_changed for x in self.results): raise ValueError("simulation count mismatch")
        exp=PolicySimulatorStatus.SIMULATIONS_READY if self.results else PolicySimulatorStatus.WAITING_FOR_CANDIDATE_POLICY_AND_CASES
        if self.status!=exp: raise ValueError("status mismatch")
        if not self.planning_only or not self.uses_real_cinematic_director or self.renders_video or self.gpu_required or self.uses_llm or self.network_calls or self.writes_runtime_config or self.activates_policy or self.auto_publication: raise ValueError("F42 guardrail violation")
        return self
