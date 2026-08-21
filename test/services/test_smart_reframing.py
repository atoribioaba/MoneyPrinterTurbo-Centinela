from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.astronomy_director import NarrativeAct
from app.models.astromedia import MediaType, Provider, Rights
from app.models.astronomical_tracker import (
    AstronomicalTrackingPlan,
    NormalizedBoundingBox,
    TrackingPoint,
    TrackingSceneResult,
    TrackingSceneStatus,
    TrackingStructuralChecks,
)
from app.models.best_moment import (
    BestMomentCandidate,
    BestMomentPlan,
    BestMomentSceneResult,
    BestMomentStatus,
    BestMomentStructuralChecks,
)
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
from app.models.shot_quality import (
    RepresentativeFrameMetrics,
    ShotQualityBand,
    ShotQualityComponents,
    ShotQualityPlan,
    ShotQualitySceneScore,
    ShotQualityStatus,
    ShotQualityStructuralChecks,
)
from app.models.smart_reframing import (
    FocalSource,
    ReframingSceneStatus,
    SmartFocalHint,
    SmartReframingRequest,
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
from app.services.smart_focal import FocalDecision, fallback_focal_decision
from app.services.smart_reframing import (
    SmartReframingError,
    SmartReframingPlanner,
    smartfocal_hint_from_decision,
)


def make_base(kind="placeholder", fit_mode=VideoFitMode.cover):
    if kind == "placeholder":
        scene = VideoBaseScenePlan(
            scene_number=1,
            scene_key="ctx-f12:scene:1",
            duration_seconds=5.0,
            visual_requirement="Visual",
            narration="Narration",
            material_selection_status=SelectionStatus.NO_ADEQUATE_MEDIA,
            render_action=VideoBaseRenderAction.PLACEHOLDER,
            fit_mode=fit_mode,
            focal_x=0.65,
            focal_y=0.40,
            renderable=True,
            clean_base_eligible=False,
            placeholder=True,
            placeholder_reason=VideoBaseBlockCode.NO_ADEQUATE_MEDIA,
        )
    else:
        media_type = (
            MediaType.IMAGE if kind == "image" else MediaType.VIDEO
        )
        action = (
            VideoBaseRenderAction.IMAGE
            if kind == "image"
            else VideoBaseRenderAction.VIDEO
        )
        scene = VideoBaseScenePlan(
            scene_number=1,
            scene_key="ctx-f12:scene:1",
            duration_seconds=5.0,
            visual_requirement="Visual",
            narration="Narration",
            material_selection_status=SelectionStatus.SELECTED,
            render_action=action,
            selected_media_id=f"{kind}-1",
            source_path=f"C:/fixture/{kind}-1.mp4",
            media_type=media_type,
            provider=Provider.OWN_MEDIA,
            rights_status=Rights.CONFIRMED_OWNED,
            publication_eligible=True,
            source_width=1920,
            source_height=1080,
            source_rotation_deg=0,
            source_duration_seconds=13.0 if kind == "video" else 0.0,
            source_start_s=0.0,
            source_fingerprint="fixture",
            fit_mode=fit_mode,
            focal_x=0.65,
            focal_y=0.40,
            renderable=True,
            clean_base_eligible=True,
            placeholder=False,
        )

    return VideoBasePlan(
        subject="F12 test",
        source_plan_context_hash="ctx-f12",
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


def make_graph(base):
    scene = base.scenes[0]
    node = VisualStoryNode(
        node_id="scene:1",
        scene_number=1,
        act=NarrativeAct.INTRODUCTION,
        duration_seconds=5.0,
        narrative_role=CinematicNarrativeRole.OPENING,
        pace=CinematicPace.MEASURED,
        intensity=0.25,
        mood=CinematicMood.DISCOVERY,
        composition_intent=CompositionIntent.BALANCED_OBSERVATION,
        motion_intent=MotionIntent.OBSERVE_LOCKED,
        transition_out_intent=TransitionIntent.FADE_OUT_INTENT,
        visual_requirement="Visual",
        astronomy_objects=[],
        subject_keys=[],
        continuity_group="act:introduction",
        placeholder=scene.placeholder,
        execution_ready=not scene.placeholder,
    )
    return VisualStoryGraph(
        subject=base.subject,
        source_plan_context_hash=base.source_plan_context_hash,
        source_video_base_version=base.version,
        source_selector_version=base.source_selector_version,
        source_cinematic_director_version="cinematic-director-v0.1",
        source_cinematic_direction_hash="direction-f12",
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
        graph_hash="graph-f12",
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_quality(base, graph):
    scene = base.scenes[0]
    if scene.placeholder:
        quality_scene = ShotQualitySceneScore(
            scene_number=1,
            node_id="scene:1",
            placeholder=True,
            status=ShotQualityStatus.NOT_SCORABLE,
            band=ShotQualityBand.NOT_SCORABLE,
        )
        scored = 0
        not_scorable = 1
        frames = 0
        mean = None
    else:
        quality_scene = ShotQualitySceneScore(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            placeholder=False,
            status=ShotQualityStatus.SCORED,
            score=0.7,
            band=ShotQualityBand.GOOD,
            components=ShotQualityComponents(
                resolution_adequacy=1.0,
                framing_efficiency=0.8,
                sharpness_relative=0.5,
                luma_range=0.8,
            ),
            frame_metrics=RepresentativeFrameMetrics(
                sample_time_s=0.0,
                blur_metric=0.2,
                y_min=4,
                y_max=180,
                y_avg=40,
                sat_avg=20,
                luma_span=176,
                ffmpeg_binary="fake",
            ),
        )
        scored = 1
        not_scorable = 0
        frames = 1
        mean = 0.7

    return ShotQualityPlan(
        subject=base.subject,
        source_plan_context_hash=base.source_plan_context_hash,
        source_video_base_version=base.version,
        source_story_graph_version=graph.version,
        source_story_graph_hash=graph.graph_hash,
        scene_count=1,
        scored_count=scored,
        not_scorable_count=not_scorable,
        analysis_failed_count=0,
        ffmpeg_frames_analyzed=frames,
        mean_score=mean,
        scenes=[quality_scene],
        structural_checks=ShotQualityStructuralChecks(
            source_alignment=True,
            graph_hash_preserved=True,
            placeholders_preserved=True,
            no_best_moment_search=True,
            no_material_search=True,
        ),
        quality_hash="quality-f12",
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_moment(base, graph, quality):
    scene = base.scenes[0]

    if scene.placeholder:
        result = BestMomentSceneResult(
            scene_number=1,
            node_id="scene:1",
            status=BestMomentStatus.PLACEHOLDER_NOT_APPLICABLE,
            source_duration_seconds=0.0,
            requested_duration_seconds=5.0,
            original_start_s=0.0,
        )
        selected = 0
        placeholders = 1
        static = 0
        frames = 0

    elif scene.media_type == MediaType.IMAGE:
        result = BestMomentSceneResult(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            status=BestMomentStatus.STATIC_IMAGE,
            source_duration_seconds=0.0,
            requested_duration_seconds=5.0,
            original_start_s=0.0,
            baseline_shot_quality_score=0.7,
        )
        selected = 0
        placeholders = 0
        static = 1
        frames = 0

    else:
        candidate = BestMomentCandidate(
            candidate_index=1,
            window_start_s=4.0,
            window_end_s=9.0,
            sample_time_s=6.5,
            blur_metric=0.1,
            luma_span=160,
            y_min=4,
            y_max=164,
            y_avg=42,
            sharpness_relative=1.0,
            luma_range_score=1.0,
            temporal_score=1.0,
        )
        result = BestMomentSceneResult(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            status=BestMomentStatus.SELECTED,
            source_duration_seconds=13.0,
            requested_duration_seconds=5.0,
            original_start_s=0.0,
            selected_start_s=4.0,
            selected_end_s=9.0,
            selected_sample_time_s=6.5,
            selected_score=1.0,
            baseline_shot_quality_score=0.7,
            candidates=[candidate],
        )
        selected = 1
        placeholders = 0
        static = 0
        frames = 1

    return BestMomentPlan(
        subject=base.subject,
        source_plan_context_hash=base.source_plan_context_hash,
        source_video_base_version=base.version,
        source_story_graph_version=graph.version,
        source_story_graph_hash=graph.graph_hash,
        source_shot_quality_version=quality.version,
        source_shot_quality_hash=quality.quality_hash,
        max_candidates=9,
        scene_count=1,
        selected_count=selected,
        placeholder_count=placeholders,
        static_image_count=static,
        analysis_failed_count=0,
        ffmpeg_frames_analyzed=frames,
        scenes=[result],
        structural_checks=BestMomentStructuralChecks(
            source_alignment=True,
            graph_hash_preserved=True,
            quality_hash_preserved=True,
            material_identity_preserved=True,
            placeholders_preserved=True,
            static_images_not_scanned=True,
        ),
        best_moment_hash="moment-f12",
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_tracking(base, graph, quality, moment, mode="none"):
    scene = base.scenes[0]

    if scene.placeholder:
        result = TrackingSceneResult(
            scene_number=1,
            node_id="scene:1",
            status=TrackingSceneStatus.PLACEHOLDER_NOT_APPLICABLE,
        )
        tracked = partial = static = seed = failed = invocations = points = 0
        placeholders = 1

    elif scene.media_type == MediaType.IMAGE:
        result = TrackingSceneResult(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            status=TrackingSceneStatus.STATIC_IMAGE_NOT_APPLICABLE,
        )
        tracked = partial = placeholders = seed = failed = invocations = points = 0
        static = 1

    elif mode in {"tracked", "partial"}:
        p1 = TrackingPoint(
            timestamp_s=4.0,
            bbox=NormalizedBoundingBox(
                x=0.10, y=0.30, width=0.10, height=0.10
            ),
            center_x=0.15,
            center_y=0.35,
        )
        p2 = TrackingPoint(
            timestamp_s=6.0,
            bbox=NormalizedBoundingBox(
                x=0.70, y=0.31, width=0.10, height=0.10
            ),
            center_x=0.75,
            center_y=0.36,
        )
        complete = mode == "tracked"
        result = TrackingSceneResult(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            status=(
                TrackingSceneStatus.TRACKED
                if complete
                else TrackingSceneStatus.TRACKED_PARTIAL
            ),
            subject_label="Luna",
            seed_source="MANUAL",
            seed_bbox=NormalizedBoundingBox(
                x=0.10, y=0.30, width=0.10, height=0.10
            ),
            window_start_s=4.0,
            window_end_s=9.0,
            backend="fake",
            complete_track=complete,
            points=[p1, p2],
        )
        tracked = 1 if complete else 0
        partial = 0 if complete else 1
        placeholders = static = seed = failed = 0
        invocations = 1
        points = 2

    else:
        result = TrackingSceneResult(
            scene_number=1,
            node_id="scene:1",
            selected_media_id=scene.selected_media_id,
            media_type=scene.media_type,
            source_path=scene.source_path,
            status=TrackingSceneStatus.SEED_REQUIRED,
            window_start_s=4.0,
            window_end_s=9.0,
        )
        tracked = partial = placeholders = static = failed = invocations = points = 0
        seed = 1

    return AstronomicalTrackingPlan(
        subject=base.subject,
        source_plan_context_hash=base.source_plan_context_hash,
        source_video_base_version=base.version,
        source_story_graph_version=graph.version,
        source_story_graph_hash=graph.graph_hash,
        source_shot_quality_version=quality.version,
        source_shot_quality_hash=quality.quality_hash,
        source_best_moment_version=moment.version,
        source_best_moment_hash=moment.best_moment_hash,
        scene_count=1,
        tracked_count=tracked,
        partial_count=partial,
        placeholder_count=placeholders,
        static_image_count=static,
        seed_required_count=seed,
        backend_unavailable_count=0,
        tracking_failed_count=failed,
        backend_invocations=invocations,
        tracking_point_count=points,
        scenes=[result],
        structural_checks=TrackingStructuralChecks(
            source_alignment=True,
            graph_hash_preserved=True,
            quality_hash_preserved=True,
            best_moment_hash_preserved=True,
            material_identity_preserved=True,
            best_moment_window_preserved=True,
            no_reframing=True,
        ),
        tracking_hash="tracking-f12",
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_request(
    kind="placeholder",
    *,
    fit_mode=VideoFitMode.cover,
    tracking_mode="none",
    hints=None,
):
    base = make_base(kind, fit_mode=fit_mode)
    graph = make_graph(base)
    quality = make_quality(base, graph)
    moment = make_moment(base, graph, quality)
    tracking = make_tracking(
        base,
        graph,
        quality,
        moment,
        mode=tracking_mode,
    )
    return SmartReframingRequest(
        video_base=base,
        story_graph=graph,
        shot_quality=quality,
        best_moment=moment,
        tracking=tracking,
        smartfocal_hints=hints or [],
    )


def strong_hint():
    return SmartFocalHint(
        scene_number=1,
        focal_x=0.80,
        focal_y=0.50,
        confidence=0.995,
        method="test",
    )


def test_placeholders_produce_no_crop():
    result = SmartReframingPlanner().build(
        make_request("placeholder")
    )

    assert result.placeholder_count == 1
    assert result.keyframe_count == 0
    assert result.execution_ready_count == 0


def test_fit_mode_is_preserved_and_skips_reframing():
    result = SmartReframingPlanner().build(
        make_request(
            "image",
            fit_mode=VideoFitMode.fit,
            hints=[strong_hint()],
        )
    )

    scene = result.scenes[0]
    assert scene.status == ReframingSceneStatus.FIT_PASSTHROUGH
    assert scene.fit_mode == VideoFitMode.fit
    assert scene.keyframes == []
    assert result.smartfocal_accepted_count == 0


def test_cover_without_tracking_or_hint_uses_f6_focal():
    result = SmartReframingPlanner().build(
        make_request("image")
    )

    scene = result.scenes[0]
    assert scene.status == ReframingSceneStatus.STATIC_F6_FOCAL
    assert scene.focal_source == FocalSource.F6_FOCAL
    assert scene.keyframes[0].focal_x == pytest.approx(0.65)


def test_strong_smartfocal_hint_is_applied():
    result = SmartReframingPlanner().build(
        make_request("image", hints=[strong_hint()])
    )

    scene = result.scenes[0]
    assert scene.status == ReframingSceneStatus.STATIC_SMARTFOCAL
    assert scene.focal_source == FocalSource.SMARTFOCAL_V01
    assert result.smartfocal_accepted_count == 1
    assert scene.keyframes[0].focal_x == pytest.approx(0.80)


def test_smartfocal_canonical_fallback_uses_safe_center():
    fallback = fallback_focal_decision()
    hint = smartfocal_hint_from_decision(
        scene_number=1,
        decision=fallback,
    )
    result = SmartReframingPlanner().build(
        make_request("image", hints=[hint])
    )

    scene = result.scenes[0]
    assert scene.status == ReframingSceneStatus.STATIC_SAFE_CENTER
    assert scene.focal_source == FocalSource.SMARTFOCAL_SAFE_CENTER
    assert result.smartfocal_rejected_count == 1
    assert scene.keyframes[0].focal_x == pytest.approx(0.5)
    assert scene.keyframes[0].focal_y == pytest.approx(0.5)


def test_nonfallback_smartfocal_does_not_invent_confidence_threshold():
    hint = SmartFocalHint(
        scene_number=1,
        focal_x=0.80,
        focal_y=0.50,
        confidence=0.01,
        method="numpy_temporal_median_cover",
    )
    result = SmartReframingPlanner().build(
        make_request("image", hints=[hint])
    )

    scene = result.scenes[0]
    assert scene.status == ReframingSceneStatus.STATIC_SMARTFOCAL
    assert scene.focal_source == FocalSource.SMARTFOCAL_V01
    assert result.smartfocal_accepted_count == 1


def test_dynamic_tracking_has_priority_over_smartfocal():
    result = SmartReframingPlanner().build(
        make_request(
            "video",
            tracking_mode="tracked",
            hints=[strong_hint()],
        )
    )

    scene = result.scenes[0]
    assert scene.status == ReframingSceneStatus.DYNAMIC_TRACKING
    assert scene.focal_source == FocalSource.F11_TRACKING
    assert len(scene.keyframes) == 2
    assert result.smartfocal_accepted_count == 0
    assert "SMARTFOCAL_HINT_SUPERSEDED_BY_F11_TRACKING" in scene.warnings


def test_dynamic_tracking_is_smoothed_and_speed_limited():
    result = SmartReframingPlanner().build(
        make_request("video", tracking_mode="tracked")
    )
    first, second = result.scenes[0].keyframes

    assert first.focal_x == pytest.approx(0.158203125)
    # Raw second center is 0.75. EMA=0.3357, below speed cap 0.36,
    # so the deterministic smoothed move remains well below the raw target.
    assert first.focal_x < second.focal_x < 0.75


def test_partial_tracking_requires_review():
    result = SmartReframingPlanner().build(
        make_request("video", tracking_mode="partial")
    )

    scene = result.scenes[0]
    assert scene.status == ReframingSceneStatus.DYNAMIC_TRACKING_PARTIAL
    assert scene.review_required is True
    assert scene.execution_ready is False


def test_cover_crop_clamps_focal_to_legal_edge():
    hint = SmartFocalHint(
        scene_number=1,
        focal_x=0.99,
        focal_y=0.5,
        confidence=0.999,
        method="test",
    )
    result = SmartReframingPlanner().build(
        make_request("image", hints=[hint])
    )
    keyframe = result.scenes[0].keyframes[0]

    assert keyframe.crop_x + keyframe.crop_width <= 1.000001
    assert keyframe.focal_x < 0.99


def test_smartfocal_bridge_preserves_canonical_decision():
    decision = FocalDecision(
        focal_x=0.8,
        focal_y=0.4,
        confidence=0.99,
        method="bridge-test",
    )
    hint = smartfocal_hint_from_decision(
        scene_number=1,
        decision=decision,
    )

    assert hint.focal_x == decision.focal_x
    assert hint.focal_y == decision.focal_y
    assert hint.confidence == decision.confidence
    assert hint.method == decision.method


def test_reframing_hash_is_deterministic():
    first = SmartReframingPlanner().build(
        make_request("video", tracking_mode="tracked")
    )
    second = SmartReframingPlanner().build(
        make_request("video", tracking_mode="tracked")
    )

    assert first.reframing_hash == second.reframing_hash


def test_tracking_hash_alignment_is_enforced():
    request = make_request("placeholder")
    request.tracking.source_best_moment_hash = "wrong"

    with pytest.raises(SmartReframingError):
        SmartReframingPlanner().build(request)


def test_duplicate_smartfocal_hints_are_rejected():
    with pytest.raises(ValidationError):
        make_request(
            "image",
            hints=[strong_hint(), strong_hint()],
        )


def test_guardrails_remain_false():
    result = SmartReframingPlanner().build(
        make_request("placeholder")
    )

    assert result.reframing_phase is True
    assert result.smartfocal_foundation_reused is True
    assert result.uses_llm is False
    assert result.gpu_required is False
    assert result.renders_video is False
    assert result.searches_material is False
    assert result.changes_material_identity is False
    assert result.changes_fit_mode is False
    assert result.best_moment_search_triggered is False
    assert result.tracking_reexecuted is False
    assert result.smartfocal_analyzer_invocations == 0
    assert result.auto_publication is False
