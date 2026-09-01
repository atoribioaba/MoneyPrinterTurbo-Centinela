from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import NarrativeAct
from app.models.astromedia import MediaType, Origin, Provider, Rights
from app.models.cinematic_director import (
    CinematicMood,
    CinematicNarrativeRole,
    CinematicPace,
    CompositionIntent,
    MotionIntent,
    TransitionIntent,
)
from app.models.master_image_i2v import (
    I2VSceneStatus,
    MasterImageI2VRequest,
)
from app.models.material_selection import SelectionStatus
from app.models.schema import VideoFitMode
from app.models.smart_ken_burns import (
    KenBurnsMotionType,
    KenBurnsScenePlan,
    KenBurnsSceneStatus,
    KenBurnsStructuralChecks,
    SmartKenBurnsPlan,
)
from app.models.video_base import (
    VideoBaseBlockCode,
    VideoBasePlan,
    VideoBaseRenderAction,
    VideoBaseRenderMode,
    VideoBaseScenePlan,
)
from app.models.visual_story_graph import (
    VisualStoryGraph,
    VisualStoryNode,
    VisualStoryStructuralChecks,
)
from app.services.master_image_i2v import (
    MasterImageI2VError,
    MasterImageI2VPlanner,
)


def make_base(
    kind="image",
    *,
    provider=Provider.OWN_MEDIA,
    rights=Rights.CONFIRMED_OWNED,
    publication_eligible=True,
):
    if kind == "placeholder":
        scene = VideoBaseScenePlan(
            scene_number=1,
            scene_key="ctx-f14:scene:1",
            duration_seconds=6.0,
            visual_requirement="Moon over a dark landscape",
            narration="Narration",
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
    else:
        media_type = MediaType.IMAGE if kind == "image" else MediaType.VIDEO
        action = (
            VideoBaseRenderAction.IMAGE
            if kind == "image"
            else VideoBaseRenderAction.VIDEO
        )
        scene = VideoBaseScenePlan(
            scene_number=1,
            scene_key="ctx-f14:scene:1",
            duration_seconds=6.0,
            visual_requirement="Moon over a dark landscape",
            narration="Narration",
            material_selection_status=SelectionStatus.SELECTED,
            render_action=action,
            selected_media_id=f"{kind}-1",
            source_path=f"C:/fixture/{kind}-1",
            media_type=media_type,
            provider=provider,
            rights_status=rights,
            publication_eligible=publication_eligible,
            source_width=2160,
            source_height=3840,
            source_rotation_deg=0,
            source_duration_seconds=10.0 if kind == "video" else 0.0,
            source_start_s=0.0,
            source_fingerprint="fixture-sha",
            fit_mode=VideoFitMode.fit,
            focal_x=0.5,
            focal_y=0.5,
            renderable=True,
            clean_base_eligible=True,
            placeholder=False,
        )

    return VideoBasePlan(
        subject="F14 test",
        source_plan_context_hash="ctx-f14",
        source_selector_version="material-selection-v0.1",
        render_mode=(
            VideoBaseRenderMode.REVIEW_PARTIAL
            if kind == "placeholder"
            else VideoBaseRenderMode.CLEAN_BASE
        ),
        requested_codec="h264_nvenc",
        scene_count=1,
        unresolved_count=1 if kind == "placeholder" else 0,
        placeholder_count=1 if kind == "placeholder" else 0,
        clean_base_eligible=kind != "placeholder",
        source_materials_publication_ready=kind != "placeholder",
        scenes=[scene],
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_graph(
    base,
    *,
    motion=MotionIntent.NATURAL_MOTION_ONLY,
):
    node = VisualStoryNode(
        node_id="scene:1",
        scene_number=1,
        act=NarrativeAct.INTRODUCTION,
        duration_seconds=6.0,
        narrative_role=CinematicNarrativeRole.OPENING,
        pace=CinematicPace.MEDITATIVE,
        intensity=0.35,
        mood=CinematicMood.DISCOVERY,
        composition_intent=CompositionIntent.BALANCED_OBSERVATION,
        motion_intent=motion,
        transition_out_intent=TransitionIntent.FADE_OUT_INTENT,
        visual_requirement="Moon over a dark landscape",
        astronomy_objects=["Moon"],
        subject_keys=["moon"],
        continuity_group="act:introduction",
        placeholder=base.scenes[0].placeholder,
        execution_ready=not base.scenes[0].placeholder,
    )

    return VisualStoryGraph(
        subject=base.subject,
        source_plan_context_hash=base.source_plan_context_hash,
        source_video_base_version=base.version,
        source_selector_version=base.source_selector_version,
        source_cinematic_director_version="cinematic-director-v0.1",
        source_cinematic_direction_hash="direction-f14",
        node_count=1,
        edge_count=0,
        placeholder_count=base.placeholder_count,
        entry_node_id="scene:1",
        climax_node_id="scene:1",
        exit_node_id="scene:1",
        topological_order=["scene:1"],
        nodes=[node],
        edges=[],
        subject_threads=[],
        act_spans=[],
        structural_checks=VisualStoryStructuralChecks(
            source_alignment=True,
            sequential_chain=True,
            entry_exit_valid=True,
            climax_connected=True,
            placeholders_preserved=True,
            topological_order_valid=True,
            subject_threads_valid=True,
        ),
        graph_hash="graph-f14",
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_ken(base, graph, *, review=False):
    scene = base.scenes[0]
    node = graph.nodes[0]

    if scene.placeholder:
        ken_scene = KenBurnsScenePlan(
            scene_number=1,
            node_id="scene:1",
            duration_seconds=6.0,
            fit_mode=scene.fit_mode,
            pace=node.pace,
            intensity=node.intensity,
            composition_intent=node.composition_intent,
            motion_intent=node.motion_intent,
            status=KenBurnsSceneStatus.PLACEHOLDER_NOT_APPLICABLE,
            motion_type=KenBurnsMotionType.HOLD,
            execution_ready=False,
            review_required=False,
        )
        counts = dict(
            placeholder_count=1,
            video_not_applicable_count=0,
            fit_static_hold_count=0,
            static_hold_count=0,
            push_in_count=0,
            pull_back_count=0,
            controlled_reveal_count=0,
            review_required_count=0,
            motion_scene_count=0,
            execution_ready_count=0,
            keyframe_count=0,
        )

    elif scene.media_type == MediaType.VIDEO:
        ken_scene = KenBurnsScenePlan(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            duration_seconds=6.0,
            fit_mode=scene.fit_mode,
            pace=node.pace,
            intensity=node.intensity,
            composition_intent=node.composition_intent,
            motion_intent=node.motion_intent,
            status=KenBurnsSceneStatus.VIDEO_NOT_APPLICABLE,
            motion_type=KenBurnsMotionType.HOLD,
            execution_ready=True,
            review_required=False,
        )
        counts = dict(
            placeholder_count=0,
            video_not_applicable_count=1,
            fit_static_hold_count=0,
            static_hold_count=0,
            push_in_count=0,
            pull_back_count=0,
            controlled_reveal_count=0,
            review_required_count=0,
            motion_scene_count=0,
            execution_ready_count=1,
            keyframe_count=0,
        )

    elif review:
        ken_scene = KenBurnsScenePlan(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            duration_seconds=6.0,
            fit_mode=scene.fit_mode,
            pace=node.pace,
            intensity=node.intensity,
            composition_intent=node.composition_intent,
            motion_intent=node.motion_intent,
            status=KenBurnsSceneStatus.REFRAMING_REVIEW_REQUIRED,
            motion_type=KenBurnsMotionType.HOLD,
            execution_ready=False,
            review_required=True,
        )
        counts = dict(
            placeholder_count=0,
            video_not_applicable_count=0,
            fit_static_hold_count=0,
            static_hold_count=0,
            push_in_count=0,
            pull_back_count=0,
            controlled_reveal_count=0,
            review_required_count=1,
            motion_scene_count=0,
            execution_ready_count=0,
            keyframe_count=0,
        )

    else:
        ken_scene = KenBurnsScenePlan(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            duration_seconds=6.0,
            fit_mode=scene.fit_mode,
            pace=node.pace,
            intensity=node.intensity,
            composition_intent=node.composition_intent,
            motion_intent=node.motion_intent,
            status=KenBurnsSceneStatus.FIT_STATIC_HOLD,
            motion_type=KenBurnsMotionType.HOLD,
            execution_ready=True,
            review_required=False,
        )
        counts = dict(
            placeholder_count=0,
            video_not_applicable_count=0,
            fit_static_hold_count=1,
            static_hold_count=0,
            push_in_count=0,
            pull_back_count=0,
            controlled_reveal_count=0,
            review_required_count=0,
            motion_scene_count=0,
            execution_ready_count=1,
            keyframe_count=0,
        )

    return SmartKenBurnsPlan(
        subject=base.subject,
        source_plan_context_hash=base.source_plan_context_hash,
        source_video_base_version=base.version,
        source_story_graph_version=graph.version,
        source_story_graph_hash=graph.graph_hash,
        source_reframing_version="smart-reframing-v0.1",
        source_reframing_hash="reframe-f14",
        target_width=base.output_width,
        target_height=base.output_height,
        target_aspect="9:16",
        scene_count=1,
        scenes=[ken_scene],
        structural_checks=KenBurnsStructuralChecks(
            source_alignment=True,
            reframing_hash_preserved=True,
            material_identity_preserved=True,
            fit_mode_preserved=True,
            target_geometry_preserved=True,
            image_only_motion=True,
            no_reframing_reexecution=True,
            no_tracking_reexecution=True,
            no_smartfocal_reexecution=True,
        ),
        ken_burns_hash="ken-f14",
        generated_at_utc=datetime.now(timezone.utc),
        **counts,
    )


def request(
    kind="image",
    *,
    provider=Provider.OWN_MEDIA,
    rights=Rights.CONFIRMED_OWNED,
    publication_eligible=True,
    approved=None,
    review=False,
    motion=MotionIntent.NATURAL_MOTION_ONLY,
):
    base = make_base(
        kind,
        provider=provider,
        rights=rights,
        publication_eligible=publication_eligible,
    )
    graph = make_graph(base, motion=motion)
    ken = make_ken(base, graph, review=review)
    return MasterImageI2VRequest(
        video_base=base,
        story_graph=graph,
        ken_burns=ken,
        approved_scene_numbers=approved or [],
    )


def test_placeholder_requires_master_image():
    result = MasterImageI2VPlanner().build(
        request("placeholder")
    )
    assert result.master_image_required_count == 1
    assert result.job_spec_count == 0


def test_video_is_not_applicable():
    result = MasterImageI2VPlanner().build(request("video"))
    assert result.video_not_applicable_count == 1
    assert result.job_spec_count == 0


def test_valid_image_waits_for_explicit_approval():
    result = MasterImageI2VPlanner().build(request("image"))
    scene = result.scenes[0]

    assert scene.status == I2VSceneStatus.AWAITING_AI_APPROVAL
    assert scene.job is not None
    assert scene.job.execution_authorized is False
    assert result.approval_pending_count == 1


def test_explicit_approval_makes_job_ready():
    result = MasterImageI2VPlanner().build(
        request("image", approved=[1])
    )
    scene = result.scenes[0]

    assert scene.status == I2VSceneStatus.I2V_JOB_READY
    assert scene.handoff_ready is True
    assert scene.job.execution_authorized is True
    assert result.job_ready_count == 1


def test_unknown_approval_is_rejected():
    with pytest.raises(MasterImageI2VError):
        MasterImageI2VPlanner().build(
            request("image", approved=[2])
        )


def test_duplicate_approval_is_rejected():
    with pytest.raises(ValidationError):
        request("image", approved=[1, 1])


def test_unverified_rights_are_blocked():
    result = MasterImageI2VPlanner().build(
        request(
            "image",
            provider=Provider.LOCAL_MEDIA,
            rights=Rights.UNVERIFIED,
            publication_eligible=False,
        )
    )
    assert result.rights_blocked_count == 1
    assert result.scenes[0].job is None


def test_restricted_rights_are_blocked():
    result = MasterImageI2VPlanner().build(
        request(
            "image",
            provider=Provider.OTHER,
            rights=Rights.RESTRICTED,
            publication_eligible=False,
        )
    )
    assert result.rights_blocked_count == 1


def test_approval_cannot_override_rights_gate():
    with pytest.raises(MasterImageI2VError):
        MasterImageI2VPlanner().build(
            request(
                "image",
                provider=Provider.LOCAL_MEDIA,
                rights=Rights.UNVERIFIED,
                publication_eligible=False,
                approved=[1],
            )
        )


def test_f13_review_blocks_i2v():
    result = MasterImageI2VPlanner().build(
        request("image", review=True)
    )
    assert result.f13_review_required_count == 1
    assert result.scenes[0].review_required is True


def test_generated_output_is_always_recreation_visual():
    result = MasterImageI2VPlanner().build(request("image"))
    job = result.scenes[0].job

    assert job.output_visual_origin == Origin.AI_GENERATED
    assert (
        job.output_scientific_status
        == ScientificStatus.RECREACION_VISUAL
    )
    assert job.disclosure_required is True


def test_ai_master_is_identified_but_output_contract_unchanged():
    result = MasterImageI2VPlanner().build(
        request(
            "image",
            provider=Provider.AI_GENERATED,
            rights=Rights.CONFIRMED_OWNED,
            publication_eligible=True,
        )
    )
    job = result.scenes[0].job

    assert job.master_image.source_origin_hint == Origin.AI_GENERATED
    assert job.output_visual_origin == Origin.AI_GENERATED


def test_own_master_is_identified_as_real_own():
    result = MasterImageI2VPlanner().build(request("image"))
    assert (
        result.scenes[0].job.master_image.source_origin_hint
        == Origin.REAL_OWN
    )


def test_prompt_contains_astronomy_preservation_constraints():
    result = MasterImageI2VPlanner().build(request("image"))
    job = result.scenes[0].job

    assert "Moon" in job.positive_prompt
    assert "Do not create new astronomical features" in job.positive_prompt
    assert "extra moon" in job.negative_prompt


def test_motion_intent_is_mapped_without_model_specific_settings():
    result = MasterImageI2VPlanner().build(
        request(
            "image",
            motion=MotionIntent.GENTLE_PULL_BACK,
        )
    )
    job = result.scenes[0].job

    assert job.motion_profile.value == "GENTLE_PULL_BACK"
    assert job.model_id is None
    assert job.adapter == "WANGP_DEFERRED_TO_F15"


def test_ken_burns_is_fallback_not_stacked():
    result = MasterImageI2VPlanner().build(request("image"))
    job = result.scenes[0].job

    assert job.ken_burns_is_fallback is True
    assert job.stack_ken_burns_with_i2v is False


def test_plan_hash_is_deterministic():
    first = MasterImageI2VPlanner().build(request("image"))
    second = MasterImageI2VPlanner().build(request("image"))

    assert first.i2v_plan_hash == second.i2v_plan_hash


def test_f13_hash_alignment_is_enforced():
    req = request("image")
    req.ken_burns.source_story_graph_hash = "wrong"

    with pytest.raises(MasterImageI2VError):
        MasterImageI2VPlanner().build(req)


def test_guardrails_remain_false():
    result = MasterImageI2VPlanner().build(request("placeholder"))

    assert result.planning_only is True
    assert result.requires_f15_backend is True
    assert result.uses_llm is False
    assert result.gpu_required is False
    assert result.renders_video is False
    assert result.downloads_models is False
    assert result.wangp_invocations == 0
    assert result.searches_material is False
    assert result.changes_material_identity is False
    assert result.best_moment_search_triggered is False
    assert result.tracking_reexecuted is False
    assert result.smartfocal_reexecuted is False
    assert result.reframing_reexecuted is False
    assert result.ken_burns_rendered is False
    assert result.auto_publication is False
