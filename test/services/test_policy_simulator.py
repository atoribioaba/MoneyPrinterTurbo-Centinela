from datetime import datetime,timezone
from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import AstronomyVideoPlan,GenerationOrigin,NarrativeAct,ScenePlan,ShotType
from app.models.material_selection import SelectionStatus
from app.models.policy_candidate import CandidatePolicy,PolicyCandidatePlan,PolicyCandidateStatus
from app.models.policy_simulator import PolicySimulationCase,PolicySimulatorRequest,PolicySimulatorStatus
from app.models.video_base import VideoBaseBlockCode,VideoBasePlan,VideoBaseRenderAction,VideoBaseRenderMode,VideoBaseScenePlan
from app.models.schema import VideoFitMode
from app.services.policy_simulator import build_policy_simulator
NOW=datetime(2026,8,22,tzinfo=timezone.utc)
def ap():
    acts=[NarrativeAct.INTRODUCTION,NarrativeAct.DEVELOPMENT,NarrativeAct.CLIMAX,NarrativeAct.RESOLUTION,NarrativeAct.EPILOGUE]
    scenes=[ScenePlan(scene_number=i,act=acts[i-1],duration_seconds=5,narration=f"N{i}",visual_requirement=f"V{i}",astronomy_objects=["Moon"],shot_type=ShotType.WIDE,material_keywords=["moon"],source_priority=["OWN_MEDIA"],transition="cut",claims=[],ai_recreation_allowed=False,scientific_status=ScientificStatus.HECHO_VERIFICADO) for i in range(1,6)]
    return AstronomyVideoPlan(subject="Moon",hook="Hook",scientific_context_summary="Context",narrative_arc=acts,scenes=scenes,epilogue="End",context_hash="ctx-f42",generation_origin=GenerationOrigin.LLM_VALIDATED,model_used="test",repair_attempted=False,total_duration_seconds=25,requires_human_review=True,approved_for_publication=False,generated_at_utc=NOW)
def vb(p):
    scenes=[VideoBaseScenePlan(scene_number=s.scene_number,scene_key=f"ctx-f42:scene:{s.scene_number}",duration_seconds=float(s.duration_seconds),visual_requirement=s.visual_requirement,narration=s.narration,material_selection_status=SelectionStatus.NO_ADEQUATE_MEDIA,render_action=VideoBaseRenderAction.PLACEHOLDER,fit_mode=VideoFitMode.fit,focal_x=.5,focal_y=.5,renderable=True,clean_base_eligible=False,placeholder=True,placeholder_reason=VideoBaseBlockCode.NO_ADEQUATE_MEDIA) for s in p.scenes]
    return VideoBasePlan(subject=p.subject,source_plan_context_hash=p.context_hash,source_selector_version="material-selection-v0.1",render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,requested_codec="h264_nvenc",scene_count=5,unresolved_count=5,placeholder_count=5,clean_base_eligible=False,source_materials_publication_ready=False,scenes=scenes,generated_at_utc=NOW)
def cp():
    c=CandidatePolicy(policy_candidate_id="p1",recommendation_id="r1",experiment_id="e1",hypothesis_id="h1",evidence_class="CONTROLLED_EXPERIMENT_RESULT",target_component="CINEMATIC_DIRECTOR_REQUEST",parameter="intensity_bias",baseline_value=0.0,candidate_value=0.05)
    return PolicyCandidatePlan(source_recommendation_gate_hash="g",status=PolicyCandidateStatus.CANDIDATE_POLICIES_READY,binding_count=1,candidate_count=1,candidates=[c],policy_candidate_hash="c",generated_at_utc=NOW)
def test_empty_waits(): assert build_policy_simulator(PolicySimulatorRequest(candidates=cp())).status==PolicySimulatorStatus.WAITING_FOR_CANDIDATE_POLICY_AND_CASES
def test_real_director_changes():
    p=ap(); r=build_policy_simulator(PolicySimulatorRequest(candidates=cp(),cases=[PolicySimulationCase(case_id="case",plan=p,video_base=vb(p))])); assert r.simulation_count==1 and r.behavior_change_count==1 and r.results[0].candidate_structural_checks_pass
def test_placeholders_preserved():
    p=ap(); r=build_policy_simulator(PolicySimulatorRequest(candidates=cp(),cases=[PolicySimulationCase(case_id="case",plan=p,video_base=vb(p))])); assert r.results[0].placeholders_preserved
def test_simulator_revalidates_direct_candidate_parameter():
    bad=cp()
    bad.candidates[0].parameter="invented_parameter"
    p=ap()
    import pytest
    with pytest.raises(RuntimeError):
        build_policy_simulator(PolicySimulatorRequest(candidates=bad,cases=[PolicySimulationCase(case_id="case",plan=p,video_base=vb(p))]))

def test_never_renders():
    r=build_policy_simulator(PolicySimulatorRequest(candidates=cp())); assert not r.renders_video and not r.gpu_required and not r.activates_policy
