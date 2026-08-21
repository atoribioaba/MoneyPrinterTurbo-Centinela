from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.astronomy_director import NarrativeAct
from app.models.astromedia import MediaType, Provider, Rights
from app.models.cinematic_director import (
    CinematicMood,
    CinematicNarrativeRole,
    CinematicPace,
    CompositionIntent,
    MotionIntent,
    TransitionIntent,
)
from app.models.material_selection import SelectionStatus
from app.models.schema import VideoFitMode
from app.models.smart_ken_burns import (
    KenBurnsMotionType,
    KenBurnsSceneStatus,
    SmartKenBurnsRequest,
)
from app.models.smart_reframing import (
    CropGeometry,
    FocalSource,
    ReframeKeyframe,
    ReframingScenePlan,
    ReframingSceneStatus,
    ReframingStructuralChecks,
    SmartReframingPlan,
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
from app.services.smart_ken_burns import (
    SmartKenBurnsError,
    SmartKenBurnsPlanner,
)


def make_base(kind="image", fit_mode=VideoFitMode.cover):
    if kind == "placeholder":
        scene = VideoBaseScenePlan(
            scene_number=1,
            scene_key="ctx-f13:scene:1",
            duration_seconds=8.0,
            visual_requirement="Visual",
            narration="Narration",
            material_selection_status=SelectionStatus.NO_ADEQUATE_MEDIA,
            render_action=VideoBaseRenderAction.PLACEHOLDER,
            fit_mode=fit_mode,
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
            scene_key="ctx-f13:scene:1",
            duration_seconds=8.0,
            visual_requirement="Visual",
            narration="Narration",
            material_selection_status=SelectionStatus.SELECTED,
            render_action=action,
            selected_media_id=f"{kind}-1",
            source_path=f"C:/fixture/{kind}-1",
            media_type=media_type,
            provider=Provider.OWN_MEDIA,
            rights_status=Rights.CONFIRMED_OWNED,
            publication_eligible=True,
            source_width=1920,
            source_height=1080,
            source_duration_seconds=12.0 if kind == "video" else 0.0,
            source_start_s=0.0,
            source_fingerprint="fixture",
            fit_mode=fit_mode,
            focal_x=0.5,
            focal_y=0.5,
            renderable=True,
            clean_base_eligible=True,
            placeholder=False,
        )

    return VideoBasePlan(
        subject="F13 test",
        source_plan_context_hash="ctx-f13",
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
    motion=MotionIntent.VERY_SLOW_PUSH,
    pace=CinematicPace.MEASURED,
    intensity=0.5,
    composition=CompositionIntent.BALANCED_OBSERVATION,
):
    node = VisualStoryNode(
        node_id="scene:1",
        scene_number=1,
        act=NarrativeAct.INTRODUCTION,
        duration_seconds=8.0,
        narrative_role=CinematicNarrativeRole.OPENING,
        pace=pace,
        intensity=intensity,
        mood=CinematicMood.DISCOVERY,
        composition_intent=composition,
        motion_intent=motion,
        transition_out_intent=TransitionIntent.FADE_OUT_INTENT,
        visual_requirement="Visual",
        astronomy_objects=[],
        subject_keys=[],
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
        source_cinematic_direction_hash="direction-f13",
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
        graph_hash="graph-f13",
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_reframing(
    base,
    graph,
    *,
    review=False,
):
    scene = base.scenes[0]

    if scene.placeholder:
        reframe_scene = ReframingScenePlan(
            scene_number=1,
            node_id="scene:1",
            fit_mode=scene.fit_mode,
            composition_intent=graph.nodes[0].composition_intent,
            motion_intent=graph.nodes[0].motion_intent,
            status=ReframingSceneStatus.PLACEHOLDER_NOT_APPLICABLE,
            focal_source=FocalSource.NONE,
            execution_ready=False,
            review_required=False,
            source_width=0,
            source_height=0,
            source_rotation_deg=0,
        )
        placeholder = 1
        fit = dynamic = partial = smart = center = f6 = 0
        ready = review_count = keys = 0

    elif scene.media_type == MediaType.VIDEO:
        key = ReframeKeyframe(
            timestamp_s=0.0,
            focal_x=0.5,
            focal_y=0.5,
            crop_x=0.341796875,
            crop_y=0.0,
            crop_width=0.31640625,
            crop_height=1.0,
            focal_source=FocalSource.F6_FOCAL,
        )
        reframe_scene = ReframingScenePlan(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            fit_mode=scene.fit_mode,
            composition_intent=graph.nodes[0].composition_intent,
            motion_intent=graph.nodes[0].motion_intent,
            status=ReframingSceneStatus.STATIC_F6_FOCAL,
            focal_source=FocalSource.F6_FOCAL,
            execution_ready=True,
            review_required=False,
            source_width=1920,
            source_height=1080,
            source_rotation_deg=0,
            crop_geometry=CropGeometry(
                crop_width_norm=0.31640625,
                crop_height_norm=1.0,
                target_aspect_ratio=0.5625,
            ),
            keyframes=[key],
        )
        placeholder = fit = dynamic = partial = smart = center = 0
        f6 = ready = keys = 1
        review_count = 0

    elif scene.fit_mode == VideoFitMode.fit:
        reframe_scene = ReframingScenePlan(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            fit_mode=scene.fit_mode,
            composition_intent=graph.nodes[0].composition_intent,
            motion_intent=graph.nodes[0].motion_intent,
            status=ReframingSceneStatus.FIT_PASSTHROUGH,
            focal_source=FocalSource.NONE,
            execution_ready=True,
            review_required=False,
            source_width=1920,
            source_height=1080,
            source_rotation_deg=0,
        )
        placeholder = dynamic = partial = smart = center = f6 = 0
        fit = ready = 1
        review_count = keys = 0

    elif review:
        reframe_scene = ReframingScenePlan(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            fit_mode=scene.fit_mode,
            composition_intent=graph.nodes[0].composition_intent,
            motion_intent=graph.nodes[0].motion_intent,
            status=ReframingSceneStatus.STATIC_F6_FOCAL,
            focal_source=FocalSource.F6_FOCAL,
            execution_ready=False,
            review_required=True,
            source_width=1920,
            source_height=1080,
            source_rotation_deg=90,
            crop_geometry=CropGeometry(
                crop_width_norm=0.31640625,
                crop_height_norm=1.0,
                target_aspect_ratio=0.5625,
            ),
            keyframes=[
                ReframeKeyframe(
                    timestamp_s=0.0,
                    focal_x=0.5,
                    focal_y=0.5,
                    crop_x=0.341796875,
                    crop_y=0.0,
                    crop_width=0.31640625,
                    crop_height=1.0,
                    focal_source=FocalSource.F6_FOCAL,
                )
            ],
        )
        placeholder = fit = dynamic = partial = smart = center = 0
        f6 = keys = review_count = 1
        ready = 0

    else:
        key = ReframeKeyframe(
            timestamp_s=0.0,
            focal_x=0.5,
            focal_y=0.5,
            crop_x=0.341796875,
            crop_y=0.0,
            crop_width=0.31640625,
            crop_height=1.0,
            focal_source=FocalSource.F6_FOCAL,
        )
        reframe_scene = ReframingScenePlan(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            fit_mode=scene.fit_mode,
            composition_intent=graph.nodes[0].composition_intent,
            motion_intent=graph.nodes[0].motion_intent,
            status=ReframingSceneStatus.STATIC_F6_FOCAL,
            focal_source=FocalSource.F6_FOCAL,
            execution_ready=True,
            review_required=False,
            source_width=1920,
            source_height=1080,
            source_rotation_deg=0,
            crop_geometry=CropGeometry(
                crop_width_norm=0.31640625,
                crop_height_norm=1.0,
                target_aspect_ratio=0.5625,
            ),
            keyframes=[key],
        )
        placeholder = fit = dynamic = partial = smart = center = 0
        f6 = ready = keys = 1
        review_count = 0

    return SmartReframingPlan(
        subject=base.subject,
        source_plan_context_hash=base.source_plan_context_hash,
        source_video_base_version=base.version,
        source_story_graph_version=graph.version,
        source_story_graph_hash=graph.graph_hash,
        source_shot_quality_version="shot-quality-v0.1",
        source_shot_quality_hash="quality-f13",
        source_best_moment_version="best-moment-v0.1",
        source_best_moment_hash="moment-f13",
        source_tracking_version="astronomical-object-tracker-v0.1",
        source_tracking_hash="tracking-f13",
        scene_count=1,
        placeholder_count=placeholder,
        fit_passthrough_count=fit,
        dynamic_tracking_count=dynamic,
        dynamic_partial_count=partial,
        static_smartfocal_count=smart,
        static_safe_center_count=center,
        static_f6_focal_count=f6,
        smartfocal_hint_count=0,
        smartfocal_accepted_count=0,
        smartfocal_rejected_count=0,
        execution_ready_count=ready,
        review_required_count=review_count,
        keyframe_count=keys,
        scenes=[reframe_scene],
        structural_checks=ReframingStructuralChecks(
            source_alignment=True,
            graph_hash_preserved=True,
            quality_hash_preserved=True,
            best_moment_hash_preserved=True,
            tracking_hash_preserved=True,
            material_identity_preserved=True,
            fit_mode_preserved=True,
            best_moment_window_preserved=True,
            smartfocal_fallback_contract_used=True,
            no_tracking_reexecution=True,
        ),
        reframing_hash="reframe-f13",
        generated_at_utc=datetime.now(timezone.utc),
    )


def build_request(
    kind="image",
    *,
    fit_mode=VideoFitMode.cover,
    motion=MotionIntent.VERY_SLOW_PUSH,
    pace=CinematicPace.MEASURED,
    intensity=0.5,
    composition=CompositionIntent.BALANCED_OBSERVATION,
    review=False,
):
    base = make_base(kind, fit_mode=fit_mode)
    graph = make_graph(
        base,
        motion=motion,
        pace=pace,
        intensity=intensity,
        composition=composition,
    )
    reframing = make_reframing(
        base,
        graph,
        review=review,
    )
    return SmartKenBurnsRequest(
        video_base=base,
        story_graph=graph,
        reframing=reframing,
    )


def test_placeholder_has_no_motion():
    result = SmartKenBurnsPlanner().build(
        build_request("placeholder")
    )

    assert result.placeholder_count == 1
    assert result.motion_scene_count == 0
    assert result.keyframe_count == 0


def test_video_is_not_animated():
    result = SmartKenBurnsPlanner().build(
        build_request("video")
    )

    scene = result.scenes[0]
    assert scene.status == KenBurnsSceneStatus.VIDEO_NOT_APPLICABLE
    assert scene.motion_type == KenBurnsMotionType.HOLD
    assert scene.keyframes == []


def test_fit_image_remains_static_without_forced_crop():
    result = SmartKenBurnsPlanner().build(
        build_request(
            "image",
            fit_mode=VideoFitMode.fit,
            motion=MotionIntent.VERY_SLOW_PUSH,
        )
    )

    scene = result.scenes[0]
    assert scene.status == KenBurnsSceneStatus.FIT_STATIC_HOLD
    assert scene.keyframes == []
    assert result.motion_scene_count == 0


def test_observe_locked_cover_image_is_hold():
    result = SmartKenBurnsPlanner().build(
        build_request(
            motion=MotionIntent.OBSERVE_LOCKED,
        )
    )

    scene = result.scenes[0]
    assert scene.status == KenBurnsSceneStatus.STATIC_HOLD
    assert scene.motion_type == KenBurnsMotionType.HOLD
    assert scene.keyframes[0].crop_width == scene.keyframes[1].crop_width
    assert scene.zoom_delta == 0.0


def test_natural_motion_only_static_image_is_hold():
    result = SmartKenBurnsPlanner().build(
        build_request(
            motion=MotionIntent.NATURAL_MOTION_ONLY,
        )
    )

    scene = result.scenes[0]
    assert scene.status == KenBurnsSceneStatus.STATIC_HOLD
    assert "STATIC_IMAGE_HAS_NO_NATURAL_MOTION_HOLD_PRESERVED" in scene.warnings


def test_very_slow_push_zooms_in():
    result = SmartKenBurnsPlanner().build(
        build_request(
            motion=MotionIntent.VERY_SLOW_PUSH,
        )
    )

    scene = result.scenes[0]
    start, end = scene.keyframes

    assert scene.status == KenBurnsSceneStatus.PUSH_IN_PLANNED
    assert start.zoom_factor == pytest.approx(1.0)
    assert end.zoom_factor > start.zoom_factor
    assert end.crop_width < start.crop_width


def test_gentle_pull_back_zooms_out():
    result = SmartKenBurnsPlanner().build(
        build_request(
            motion=MotionIntent.GENTLE_PULL_BACK,
        )
    )

    scene = result.scenes[0]
    start, end = scene.keyframes

    assert scene.status == KenBurnsSceneStatus.PULL_BACK_PLANNED
    assert start.zoom_factor > end.zoom_factor
    assert end.zoom_factor == pytest.approx(1.0)


def test_controlled_reveal_moves_toward_f12_focal():
    result = SmartKenBurnsPlanner().build(
        build_request(
            motion=MotionIntent.CONTROLLED_REVEAL,
            composition=CompositionIntent.LAYERED_WIDE,
        )
    )

    scene = result.scenes[0]
    start, end = scene.keyframes

    assert scene.status == KenBurnsSceneStatus.CONTROLLED_REVEAL_PLANNED
    assert start.focal_y != end.focal_y
    assert end.focal_x == pytest.approx(0.5)
    assert end.focal_y == pytest.approx(0.5)


def test_zoom_delta_respects_maximum():
    request = build_request(
        motion=MotionIntent.VERY_SLOW_PUSH,
        pace=CinematicPace.PEAK,
        intensity=1.0,
    )
    request.max_zoom_delta = 0.05

    result = SmartKenBurnsPlanner().build(request)

    assert result.scenes[0].zoom_delta == pytest.approx(0.05)


def test_reframing_review_blocks_motion():
    result = SmartKenBurnsPlanner().build(
        build_request(
            motion=MotionIntent.VERY_SLOW_PUSH,
            review=True,
        )
    )

    scene = result.scenes[0]
    assert scene.status == KenBurnsSceneStatus.REFRAMING_REVIEW_REQUIRED
    assert scene.review_required is True
    assert scene.execution_ready is False
    assert scene.keyframes == []


def test_keyframes_preserve_nine_sixteen_crop_aspect():
    result = SmartKenBurnsPlanner().build(
        build_request(
            motion=MotionIntent.VERY_SLOW_PUSH,
        )
    )

    for key in result.scenes[0].keyframes:
        assert key.crop_width / key.crop_height == pytest.approx(
            0.31640625,
            rel=1e-6,
        )


def test_keyframes_never_leave_source_bounds():
    result = SmartKenBurnsPlanner().build(
        build_request(
            motion=MotionIntent.CONTROLLED_REVEAL,
        )
    )

    for key in result.scenes[0].keyframes:
        assert key.crop_x >= 0.0
        assert key.crop_y >= 0.0
        assert key.crop_x + key.crop_width <= 1.000001
        assert key.crop_y + key.crop_height <= 1.000001


def test_hash_is_deterministic():
    first = SmartKenBurnsPlanner().build(
        build_request(
            motion=MotionIntent.CONTROLLED_REVEAL,
        )
    )
    second = SmartKenBurnsPlanner().build(
        build_request(
            motion=MotionIntent.CONTROLLED_REVEAL,
        )
    )

    assert first.ken_burns_hash == second.ken_burns_hash


def test_reframing_hash_alignment_is_preserved():
    request = build_request()
    request.reframing.source_story_graph_hash = "wrong"

    with pytest.raises(SmartKenBurnsError):
        SmartKenBurnsPlanner().build(request)


def test_guardrails_remain_false():
    result = SmartKenBurnsPlanner().build(
        build_request("placeholder")
    )

    assert result.ken_burns_phase is True
    assert result.normalized_geometry is True
    assert result.uses_llm is False
    assert result.gpu_required is False
    assert result.renders_video is False
    assert result.searches_material is False
    assert result.changes_material_identity is False
    assert result.changes_fit_mode is False
    assert result.best_moment_search_triggered is False
    assert result.tracking_reexecuted is False
    assert result.smartfocal_reexecuted is False
    assert result.reframing_reexecuted is False
    assert result.auto_publication is False
