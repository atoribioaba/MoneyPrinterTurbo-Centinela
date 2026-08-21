from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.astronomy_director import NarrativeAct
from app.models.astromedia import MediaType, Provider, Rights
from app.models.astronomical_tracker import (
    AstronomicalTrackingRequest,
    NormalizedBoundingBox,
    TrackingPoint,
    TrackingSceneStatus,
    TrackingSeed,
)
from app.models.best_moment import (
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
from app.models.video_base import (
    VideoBaseBlockCode,
    VideoBasePlan,
    VideoBaseRenderAction,
    VideoBaseRenderMode,
    VideoBaseScenePlan,
)
from app.models.visual_story_graph import (
    CompositionLinkType,
    NarrativeLinkType,
    SubjectLinkType,
    VisualStoryEdge,
    VisualStoryGraph,
    VisualStoryNode,
    VisualStoryStructuralChecks,
)
from app.services.astronomical_tracker import (
    AstronomicalObjectTracker,
    AstronomicalTrackingError,
    BackendTrackResult,
)


def make_base(kind="placeholder"):
    scenes = []
    for number in range(1, 6):
        if kind == "placeholder":
            scenes.append(
                VideoBaseScenePlan(
                    scene_number=number,
                    scene_key=f"ctx-f11:scene:{number}",
                    duration_seconds=5.0,
                    visual_requirement=f"Visual {number}",
                    narration=f"Narration {number}",
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
            )
        elif kind == "image":
            scenes.append(
                VideoBaseScenePlan(
                    scene_number=number,
                    scene_key=f"ctx-f11:scene:{number}",
                    duration_seconds=5.0,
                    visual_requirement=f"Visual {number}",
                    narration=f"Narration {number}",
                    material_selection_status=SelectionStatus.SELECTED,
                    render_action=VideoBaseRenderAction.IMAGE,
                    selected_media_id=f"image-{number}",
                    source_path=f"C:/fixture/image-{number}.jpg",
                    media_type=MediaType.IMAGE,
                    provider=Provider.OWN_MEDIA,
                    rights_status=Rights.CONFIRMED_OWNED,
                    publication_eligible=True,
                    source_width=2160,
                    source_height=3840,
                    source_duration_seconds=0.0,
                    source_start_s=0.0,
                    source_fingerprint="fixture",
                    fit_mode=VideoFitMode.fit,
                    focal_x=0.5,
                    focal_y=0.5,
                    renderable=True,
                    clean_base_eligible=True,
                    placeholder=False,
                )
            )
        else:
            scenes.append(
                VideoBaseScenePlan(
                    scene_number=number,
                    scene_key=f"ctx-f11:scene:{number}",
                    duration_seconds=5.0,
                    visual_requirement=f"Visual {number}",
                    narration=f"Narration {number}",
                    material_selection_status=SelectionStatus.SELECTED,
                    render_action=VideoBaseRenderAction.VIDEO,
                    selected_media_id=f"video-{number}",
                    source_path=f"C:/fixture/video-{number}.mp4",
                    media_type=MediaType.VIDEO,
                    provider=Provider.OWN_MEDIA,
                    rights_status=Rights.CONFIRMED_OWNED,
                    publication_eligible=True,
                    source_width=1920,
                    source_height=1080,
                    source_duration_seconds=13.0,
                    source_start_s=0.0,
                    source_fingerprint="fixture",
                    fit_mode=VideoFitMode.cover,
                    focal_x=0.5,
                    focal_y=0.5,
                    renderable=True,
                    clean_base_eligible=True,
                    placeholder=False,
                )
            )

    return VideoBasePlan(
        subject="F11 test",
        source_plan_context_hash="ctx-f11",
        source_selector_version="material-selection-v0.1",
        render_mode=(
            VideoBaseRenderMode.REVIEW_PARTIAL
            if kind == "placeholder"
            else VideoBaseRenderMode.CLEAN_BASE
        ),
        requested_codec="h264_nvenc",
        scene_count=5,
        unresolved_count=5 if kind == "placeholder" else 0,
        placeholder_count=5 if kind == "placeholder" else 0,
        clean_base_eligible=kind != "placeholder",
        source_materials_publication_ready=kind != "placeholder",
        scenes=scenes,
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_graph(base):
    intensities = [0.25, 0.57, 0.9, 0.49, 0.21]
    acts = [
        NarrativeAct.INTRODUCTION,
        NarrativeAct.DEVELOPMENT,
        NarrativeAct.CLIMAX,
        NarrativeAct.RESOLUTION,
        NarrativeAct.EPILOGUE,
    ]
    roles = [
        CinematicNarrativeRole.OPENING,
        CinematicNarrativeRole.BUILD,
        CinematicNarrativeRole.PEAK,
        CinematicNarrativeRole.RELEASE,
        CinematicNarrativeRole.AFTERGLOW,
    ]

    nodes = []
    for number, scene in enumerate(base.scenes, start=1):
        nodes.append(
            VisualStoryNode(
                node_id=f"scene:{number}",
                scene_number=number,
                act=acts[number - 1],
                duration_seconds=5.0,
                narrative_role=roles[number - 1],
                pace=CinematicPace.MEASURED,
                intensity=intensities[number - 1],
                mood=CinematicMood.DISCOVERY,
                composition_intent=CompositionIntent.BALANCED_OBSERVATION,
                motion_intent=MotionIntent.OBSERVE_LOCKED,
                transition_out_intent=(
                    TransitionIntent.FADE_OUT_INTENT
                    if number == 5
                    else TransitionIntent.SOFT_CUT
                ),
                visual_requirement=f"Visual {number}",
                astronomy_objects=[],
                subject_keys=[],
                continuity_group=f"act:{acts[number - 1].value}",
                placeholder=scene.placeholder,
                execution_ready=not scene.placeholder,
            )
        )

    edges = [
        VisualStoryEdge(
            edge_id=f"scene:{number}->scene:{number+1}",
            source_node_id=f"scene:{number}",
            target_node_id=f"scene:{number+1}",
            source_scene_number=number,
            target_scene_number=number + 1,
            narrative_link=NarrativeLinkType.ACT_TRANSITION,
            subject_link=SubjectLinkType.UNDEFINED,
            composition_link=CompositionLinkType.HOLD,
            intensity_delta=0.0,
            source_transition_intent=TransitionIntent.SOFT_CUT,
            cut_motivation="fixture",
        )
        for number in range(1, 5)
    ]

    return VisualStoryGraph(
        subject=base.subject,
        source_plan_context_hash=base.source_plan_context_hash,
        source_video_base_version=base.version,
        source_selector_version=base.source_selector_version,
        source_cinematic_director_version="cinematic-director-v0.1",
        source_cinematic_direction_hash="direction-hash",
        node_count=5,
        edge_count=4,
        placeholder_count=base.placeholder_count,
        entry_node_id="scene:1",
        climax_node_id="scene:3",
        exit_node_id="scene:5",
        topological_order=[f"scene:{n}" for n in range(1, 6)],
        nodes=nodes,
        edges=edges,
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
        graph_hash="graph-f11",
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_quality(base, graph):
    scenes = []
    for scene in base.scenes:
        if scene.placeholder:
            scenes.append(
                ShotQualitySceneScore(
                    scene_number=scene.scene_number,
                    node_id=f"scene:{scene.scene_number}",
                    selected_media_id=scene.selected_media_id,
                    media_type=scene.media_type,
                    source_path=scene.source_path,
                    placeholder=True,
                    status=ShotQualityStatus.NOT_SCORABLE,
                    score=None,
                    band=ShotQualityBand.NOT_SCORABLE,
                )
            )
        else:
            scenes.append(
                ShotQualitySceneScore(
                    scene_number=scene.scene_number,
                    node_id=f"scene:{scene.scene_number}",
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
            )

    return ShotQualityPlan(
        subject=base.subject,
        source_plan_context_hash=base.source_plan_context_hash,
        source_video_base_version=base.version,
        source_story_graph_version=graph.version,
        source_story_graph_hash=graph.graph_hash,
        scene_count=5,
        scored_count=0 if base.placeholder_count else 5,
        not_scorable_count=base.placeholder_count,
        analysis_failed_count=0,
        ffmpeg_frames_analyzed=0 if base.placeholder_count else 5,
        mean_score=None if base.placeholder_count else 0.7,
        scenes=scenes,
        structural_checks=ShotQualityStructuralChecks(
            source_alignment=True,
            graph_hash_preserved=True,
            placeholders_preserved=True,
            no_best_moment_search=True,
            no_material_search=True,
        ),
        quality_hash="quality-f11",
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_moment(base, graph, quality):
    scenes = []
    for scene in base.scenes:
        if scene.placeholder:
            status = BestMomentStatus.PLACEHOLDER_NOT_APPLICABLE
            kwargs = {}
        elif scene.media_type == MediaType.IMAGE:
            status = BestMomentStatus.STATIC_IMAGE
            kwargs = {}
        else:
            status = BestMomentStatus.SELECTED
            kwargs = {
                "selected_start_s": 4.0,
                "selected_end_s": 9.0,
                "selected_sample_time_s": 6.5,
                "selected_score": 0.9,
                "candidates": [
                    {
                        "candidate_index": 1,
                        "window_start_s": 4.0,
                        "window_end_s": 9.0,
                        "sample_time_s": 6.5,
                        "blur_metric": 0.1,
                        "luma_span": 160,
                        "y_min": 4,
                        "y_max": 164,
                        "y_avg": 42,
                        "sharpness_relative": 1.0,
                        "luma_range_score": 1.0,
                        "temporal_score": 1.0,
                    }
                ],
            }

        scenes.append(
            BestMomentSceneResult(
                scene_number=scene.scene_number,
                node_id=f"scene:{scene.scene_number}",
                selected_media_id=scene.selected_media_id,
                media_type=scene.media_type,
                source_path=scene.source_path,
                status=status,
                source_duration_seconds=scene.source_duration_seconds,
                requested_duration_seconds=scene.duration_seconds,
                original_start_s=scene.source_start_s,
                baseline_shot_quality_score=(
                    None if scene.placeholder else 0.7
                ),
                **kwargs,
            )
        )

    selected = sum(
        scene.status == BestMomentStatus.SELECTED for scene in scenes
    )
    placeholders = sum(
        scene.status == BestMomentStatus.PLACEHOLDER_NOT_APPLICABLE
        for scene in scenes
    )
    static = sum(
        scene.status == BestMomentStatus.STATIC_IMAGE for scene in scenes
    )

    return BestMomentPlan(
        subject=base.subject,
        source_plan_context_hash=base.source_plan_context_hash,
        source_video_base_version=base.version,
        source_story_graph_version=graph.version,
        source_story_graph_hash=graph.graph_hash,
        source_shot_quality_version=quality.version,
        source_shot_quality_hash=quality.quality_hash,
        max_candidates=9,
        scene_count=5,
        selected_count=selected,
        placeholder_count=placeholders,
        static_image_count=static,
        analysis_failed_count=0,
        ffmpeg_frames_analyzed=selected,
        scenes=scenes,
        structural_checks=BestMomentStructuralChecks(
            source_alignment=True,
            graph_hash_preserved=True,
            quality_hash_preserved=True,
            material_identity_preserved=True,
            placeholders_preserved=True,
            static_images_not_scanned=True,
        ),
        best_moment_hash="moment-f11",
        generated_at_utc=datetime.now(timezone.utc),
    )


class NeverBackend:
    calls = 0

    def track(self, **kwargs):
        self.calls += 1
        raise AssertionError("backend must not run")


class FakeBackend:
    def __init__(self, complete=True):
        self.calls = 0
        self.complete = complete

    def track(
        self,
        *,
        source_path,
        start_s,
        end_s,
        seed_bbox,
        sample_rate_hz,
    ):
        self.calls += 1
        second = NormalizedBoundingBox(
            x=min(0.7, seed_bbox.x + 0.02),
            y=min(0.7, seed_bbox.y + 0.01),
            width=seed_bbox.width,
            height=seed_bbox.height,
        )
        return BackendTrackResult(
            points=[
                TrackingPoint(
                    timestamp_s=start_s,
                    bbox=seed_bbox,
                    center_x=seed_bbox.x + seed_bbox.width / 2,
                    center_y=seed_bbox.y + seed_bbox.height / 2,
                ),
                TrackingPoint(
                    timestamp_s=end_s,
                    bbox=second,
                    center_x=second.x + second.width / 2,
                    center_y=second.y + second.height / 2,
                ),
            ],
            complete=self.complete,
            warnings=[] if self.complete else ["TRACK_LOST_AT=8.0"],
        )


def build_request(kind, seeds=None):
    base = make_base(kind)
    graph = make_graph(base)
    quality = make_quality(base, graph)
    moment = make_moment(base, graph, quality)
    return AstronomicalTrackingRequest(
        video_base=base,
        story_graph=graph,
        shot_quality=quality,
        best_moment=moment,
        seeds=seeds or [],
    )


def seed_for(scene_number):
    return TrackingSeed(
        scene_number=scene_number,
        subject_label="Luna",
        bbox=NormalizedBoundingBox(
            x=0.4,
            y=0.3,
            width=0.2,
            height=0.2,
        ),
    )


def test_placeholders_never_invoke_backend():
    backend = NeverBackend()
    result = AstronomicalObjectTracker(backend=backend).build(
        build_request("placeholder")
    )

    assert result.placeholder_count == 5
    assert result.tracked_count == 0
    assert result.backend_invocations == 0
    assert result.tracking_point_count == 0
    assert backend.calls == 0


def test_static_images_never_invoke_backend():
    backend = NeverBackend()
    result = AstronomicalObjectTracker(backend=backend).build(
        build_request("image")
    )

    assert result.static_image_count == 5
    assert result.tracked_count == 0
    assert result.backend_invocations == 0
    assert backend.calls == 0


def test_video_without_seed_reports_seed_required():
    backend = NeverBackend()
    result = AstronomicalObjectTracker(backend=backend).build(
        build_request("video")
    )

    assert result.seed_required_count == 5
    assert result.tracked_count == 0
    assert result.backend_invocations == 0
    assert backend.calls == 0


def test_video_with_explicit_seed_tracks_inside_f10_window():
    seeds = [seed_for(number) for number in range(1, 6)]
    backend = FakeBackend(complete=True)
    result = AstronomicalObjectTracker(backend=backend).build(
        build_request("video", seeds=seeds)
    )

    assert result.tracked_count == 5
    assert result.partial_count == 0
    assert result.backend_invocations == 5
    assert result.tracking_point_count == 10
    assert backend.calls == 5

    first = result.scenes[0]
    assert first.status == TrackingSceneStatus.TRACKED
    assert first.window_start_s == pytest.approx(4.0)
    assert first.window_end_s == pytest.approx(9.0)
    assert first.points[0].timestamp_s == pytest.approx(4.0)
    assert first.subject_label == "Luna"


def test_partial_track_is_explicit():
    backend = FakeBackend(complete=False)
    result = AstronomicalObjectTracker(backend=backend).build(
        build_request("video", seeds=[seed_for(n) for n in range(1, 6)])
    )

    assert result.tracked_count == 0
    assert result.partial_count == 5
    assert all(
        scene.status == TrackingSceneStatus.TRACKED_PARTIAL
        for scene in result.scenes
    )


def test_tracking_hash_is_deterministic():
    seeds = [seed_for(number) for number in range(1, 6)]

    first = AstronomicalObjectTracker(
        backend=FakeBackend()
    ).build(build_request("video", seeds=seeds))

    second = AstronomicalObjectTracker(
        backend=FakeBackend()
    ).build(build_request("video", seeds=seeds))

    assert first.tracking_hash == second.tracking_hash


def test_placeholder_seed_is_rejected():
    with pytest.raises(AstronomicalTrackingError):
        AstronomicalObjectTracker(backend=NeverBackend()).build(
            build_request("placeholder", seeds=[seed_for(1)])
        )


def test_best_moment_hash_alignment_is_enforced():
    request = build_request("placeholder")
    request.best_moment.source_shot_quality_hash = "wrong"

    with pytest.raises(AstronomicalTrackingError):
        AstronomicalObjectTracker(backend=NeverBackend()).build(request)


def test_guardrails_remain_false():
    result = AstronomicalObjectTracker(
        backend=NeverBackend()
    ).build(build_request("placeholder"))

    assert result.tracking_phase is True
    assert result.uses_llm is False
    assert result.gpu_required is False
    assert result.renders_video is False
    assert result.searches_material is False
    assert result.changes_material_identity is False
    assert result.best_moment_search_triggered is False
    assert result.smartfocal_triggered is False
    assert result.reframing_triggered is False
    assert result.auto_publication is False
