from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.astronomy_director import NarrativeAct
from app.models.astromedia import MediaType, Provider, Rights
from app.models.best_moment import (
    BestMomentRequest,
    BestMomentStatus,
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
from app.services.best_moment import (
    BestMomentDetector,
    BestMomentError,
    _candidate_starts,
)


def make_base(kind="placeholder"):
    scenes = []
    for number in range(1, 6):
        if kind == "placeholder":
            scenes.append(
                VideoBaseScenePlan(
                    scene_number=number,
                    scene_key=f"ctx-f10:scene:{number}",
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
                    scene_key=f"ctx-f10:scene:{number}",
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
                    scene_key=f"ctx-f10:scene:{number}",
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
        subject="F10 test",
        source_plan_context_hash="ctx-f10",
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
        graph_hash="graph-f10",
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
        quality_hash="quality-f10",
        generated_at_utc=datetime.now(timezone.utc),
    )


class NeverAnalyzer:
    calls = 0
    def analyze(self, scene):
        self.calls += 1
        raise AssertionError("analyzer must not run")


class FakeAnalyzer:
    def __init__(self):
        self.calls = 0

    def analyze(self, scene):
        self.calls += 1
        # Best around t=6.5s: low blur + high tonal span.
        distance = abs(scene.source_start_s - 6.5)
        blur = 0.05 + distance * 0.05
        span = max(32.0, 180.0 - distance * 10.0)
        return RepresentativeFrameMetrics(
            sample_time_s=scene.source_start_s,
            blur_metric=blur,
            y_min=4,
            y_max=min(220.0, 4 + span),
            y_avg=42,
            sat_avg=30,
            luma_span=span,
            ffmpeg_binary="fake",
        )


def request_for(kind, analyzer=None):
    base = make_base(kind)
    graph = make_graph(base)
    quality = make_quality(base, graph)
    return (
        BestMomentRequest(
            video_base=base,
            story_graph=graph,
            shot_quality=quality,
            max_candidates=9,
        ),
        analyzer,
    )


def test_placeholders_do_not_trigger_temporal_scan():
    req, analyzer = request_for("placeholder", NeverAnalyzer())
    result = BestMomentDetector(analyzer=analyzer).build(req)

    assert result.placeholder_count == 5
    assert result.selected_count == 0
    assert result.ffmpeg_frames_analyzed == 0
    assert analyzer.calls == 0
    assert all(
        scene.status == BestMomentStatus.PLACEHOLDER_NOT_APPLICABLE
        for scene in result.scenes
    )


def test_static_images_do_not_trigger_temporal_scan():
    req, analyzer = request_for("image", NeverAnalyzer())
    result = BestMomentDetector(analyzer=analyzer).build(req)

    assert result.static_image_count == 5
    assert result.selected_count == 0
    assert result.ffmpeg_frames_analyzed == 0
    assert analyzer.calls == 0
    assert all(
        scene.status == BestMomentStatus.STATIC_IMAGE
        for scene in result.scenes
    )


def test_video_selects_best_window_deterministically():
    analyzer = FakeAnalyzer()
    req, _ = request_for("video", analyzer)
    result = BestMomentDetector(analyzer=analyzer).build(req)

    assert result.selected_count == 5
    assert result.analysis_failed_count == 0
    assert result.ffmpeg_frames_analyzed == 45
    assert analyzer.calls == 45

    first = result.scenes[0]
    assert first.status == BestMomentStatus.SELECTED
    assert len(first.candidates) == 9
    assert first.selected_start_s == pytest.approx(4.0)
    assert first.selected_sample_time_s == pytest.approx(6.5)


def test_candidate_starts_cover_entire_valid_start_range():
    starts = _candidate_starts(
        source_duration=13.0,
        requested_duration=5.0,
        max_candidates=9,
    )
    assert starts == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]


def test_short_or_exact_source_has_single_candidate():
    assert _candidate_starts(
        source_duration=5.0,
        requested_duration=5.0,
        max_candidates=9,
    ) == [0.0]


def test_hash_is_deterministic():
    req1, _ = request_for("video", FakeAnalyzer())
    req2, _ = request_for("video", FakeAnalyzer())

    first = BestMomentDetector(analyzer=FakeAnalyzer()).build(req1)
    second = BestMomentDetector(analyzer=FakeAnalyzer()).build(req2)

    assert first.best_moment_hash == second.best_moment_hash


def test_quality_hash_mismatch_is_rejected():
    base = make_base("placeholder")
    graph = make_graph(base)
    quality = make_quality(base, graph)
    quality.source_story_graph_hash = "wrong"

    with pytest.raises(BestMomentError):
        BestMomentDetector(analyzer=NeverAnalyzer()).build(
            BestMomentRequest(
                video_base=base,
                story_graph=graph,
                shot_quality=quality,
            )
        )


def test_guardrails_are_false():
    req, analyzer = request_for("placeholder", NeverAnalyzer())
    result = BestMomentDetector(analyzer=analyzer).build(req)

    assert result.uses_llm is False
    assert result.gpu_required is False
    assert result.renders_video is False
    assert result.searches_material is False
    assert result.changes_material_identity is False
    assert result.tracking_triggered is False
    assert result.smartfocal_triggered is False
    assert result.auto_publication is False
