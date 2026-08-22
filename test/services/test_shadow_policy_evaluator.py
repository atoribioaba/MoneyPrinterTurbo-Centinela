from datetime import datetime, timezone

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import AstronomyVideoPlan, GenerationOrigin, NarrativeAct, ScenePlan, ShotType
from app.models.material_selection import SelectionStatus
from app.models.policy_candidate import PolicyTargetComponent
from app.models.policy_registry import PolicyRegistryEntry, PolicyRegistryPlan, PolicyRegistryStatus
from app.models.policy_simulator import PolicySimulationCase
from app.models.schema import VideoFitMode
from app.models.shadow_policy_evaluator import ShadowPolicyRequest, ShadowPolicyStatus
from app.models.video_base import VideoBaseBlockCode, VideoBasePlan, VideoBaseRenderAction, VideoBaseRenderMode, VideoBaseScenePlan
from app.services.shadow_policy_evaluator import build_shadow_policy_plan

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def astronomy_plan():
    acts = [
        NarrativeAct.INTRODUCTION,
        NarrativeAct.DEVELOPMENT,
        NarrativeAct.CLIMAX,
        NarrativeAct.RESOLUTION,
        NarrativeAct.EPILOGUE,
    ]
    scenes = [
        ScenePlan(
            scene_number=i,
            act=acts[i - 1],
            duration_seconds=5,
            narration=f"N{i}",
            visual_requirement=f"V{i}",
            astronomy_objects=["Moon"],
            shot_type=ShotType.WIDE,
            material_keywords=["moon"],
            source_priority=["OWN_MEDIA"],
            transition="cut",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        )
        for i in range(1, 6)
    ]
    return AstronomyVideoPlan(
        subject="Moon",
        hook="Hook",
        scientific_context_summary="Context",
        narrative_arc=acts,
        scenes=scenes,
        epilogue="End",
        context_hash="ctx-f46",
        generation_origin=GenerationOrigin.LLM_VALIDATED,
        model_used="test",
        repair_attempted=False,
        total_duration_seconds=25,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=NOW,
    )


def video_base(plan):
    scenes = [
        VideoBaseScenePlan(
            scene_number=s.scene_number,
            scene_key=f"ctx-f46:scene:{s.scene_number}",
            duration_seconds=float(s.duration_seconds),
            visual_requirement=s.visual_requirement,
            narration=s.narration,
            material_selection_status=SelectionStatus.NO_ADEQUATE_MEDIA,
            render_action=VideoBaseRenderAction.PLACEHOLDER,
            fit_mode=VideoFitMode.fit,
            focal_x=0.5,
            focal_y=0.5,
            renderable=True,
            clean_base_eligible=False,
            placeholder=True,
            placeholder_reason=VideoBaseBlockCode.NO_ADEQUATE_MEDIA,
        )
        for s in plan.scenes
    ]
    return VideoBasePlan(
        subject=plan.subject,
        source_plan_context_hash=plan.context_hash,
        source_selector_version="material-selection-v0.1",
        render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
        requested_codec="h264_nvenc",
        scene_count=5,
        unresolved_count=5,
        placeholder_count=5,
        clean_base_eligible=False,
        source_materials_publication_ready=False,
        scenes=scenes,
        generated_at_utc=NOW,
    )


def registry(with_entry=True):
    entries = []
    if with_entry:
        entries = [
            PolicyRegistryEntry(
                policy_version="policy-v1",
                policy_candidate_id="candidate-1",
                approval_record_hash="approval-1",
                target_component=PolicyTargetComponent.CINEMATIC_DIRECTOR_REQUEST,
                parameter="intensity_bias",
                baseline_value=0.0,
                candidate_value=0.05,
                previous_policy_version=None,
                rollback_target_policy_version=None,
            )
        ]
    return PolicyRegistryPlan(
        source_policy_candidate_hash="candidate-hash",
        source_human_policy_approval_hash="approval-hash",
        rollback_metadata_generated=bool(entries),
        status=PolicyRegistryStatus.VERSIONED_POLICIES_REGISTERED if entries else PolicyRegistryStatus.WAITING_FOR_APPROVED_POLICY,
        entry_count=len(entries),
        entries=entries,
        policy_registry_hash="registry-hash",
        generated_at_utc=NOW,
    )


def test_empty_cases_wait():
    result = build_shadow_policy_plan(ShadowPolicyRequest(registry=registry(), cases=[]))
    assert result.status == ShadowPolicyStatus.WAITING_FOR_REGISTERED_POLICY_AND_CASES


def test_real_shadow_changes_direction_without_runtime_effect():
    plan = astronomy_plan()
    result = build_shadow_policy_plan(
        ShadowPolicyRequest(
            registry=registry(),
            cases=[PolicySimulationCase(case_id="case-1", plan=plan, video_base=video_base(plan))],
        )
    )
    assert result.status == ShadowPolicyStatus.SHADOW_RESULTS_READY
    assert result.evaluation_count == 1
    assert result.behavior_change_count == 1
    assert result.runtime_effect is False
    assert result.activates_policy is False


def test_shadow_preserves_structural_guardrails():
    plan = astronomy_plan()
    result = build_shadow_policy_plan(
        ShadowPolicyRequest(
            registry=registry(),
            cases=[PolicySimulationCase(case_id="case-1", plan=plan, video_base=video_base(plan))],
        )
    )
    assert result.safe_evaluation_count == 1
    assert result.results[0].placeholders_preserved is True
    assert result.results[0].candidate_structural_checks_pass is True
