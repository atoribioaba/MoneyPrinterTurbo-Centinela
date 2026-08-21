from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.astromedia import MediaType, Provider, Rights
from app.models.schema import VideoFitMode
from app.models.shot_quality import (
    RepresentativeFrameMetrics,
    ShotQualityBand,
    ShotQualityRequest,
    ShotQualityStatus,
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
from app.models.astronomy_director import NarrativeAct
from app.models.cinematic_director import (
    CinematicMood,
    CinematicNarrativeRole,
    CinematicPace,
    CompositionIntent,
    MotionIntent,
    TransitionIntent,
)
from app.models.material_selection import SelectionStatus
from app.services.shot_quality import (
    FFmpegFrameDiagnostics,
    ShotQualityError,
    ShotQualityScorer,
)


def make_base(*, placeholders=True, source_paths=None):
    scenes = []
    source_paths = source_paths or {}

    for number in range(1, 6):
        placeholder = placeholders
        if placeholder:
            scenes.append(
                VideoBaseScenePlan(
                    scene_number=number,
                    scene_key=f"ctx-f9:scene:{number}",
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
        else:
            path = source_paths[number]
            scenes.append(
                VideoBaseScenePlan(
                    scene_number=number,
                    scene_key=f"ctx-f9:scene:{number}",
                    duration_seconds=5.0,
                    visual_requirement=f"Visual {number}",
                    narration=f"Narration {number}",
                    material_selection_status=SelectionStatus.SELECTED,
                    render_action=VideoBaseRenderAction.IMAGE,
                    selected_media_id=f"media-{number}",
                    source_path=str(path),
                    media_type=MediaType.IMAGE,
                    provider=Provider.OWN_MEDIA,
                    rights_status=Rights.CONFIRMED_OWNED,
                    publication_eligible=True,
                    source_width=2160,
                    source_height=3840,
                    source_rotation_deg=0,
                    source_duration_seconds=0.0,
                    source_start_s=0.0,
                    source_fingerprint="test",
                    fit_mode=VideoFitMode.fit,
                    focal_x=0.5,
                    focal_y=0.5,
                    renderable=True,
                    clean_base_eligible=True,
                    placeholder=False,
                )
            )

    return VideoBasePlan(
        subject="F9 test",
        source_plan_context_hash="ctx-f9",
        source_selector_version="material-selection-v0.1",
        render_mode=(
            VideoBaseRenderMode.REVIEW_PARTIAL
            if placeholders
            else VideoBaseRenderMode.CLEAN_BASE
        ),
        requested_codec="h264_nvenc",
        scene_count=5,
        unresolved_count=5 if placeholders else 0,
        placeholder_count=5 if placeholders else 0,
        clean_base_eligible=not placeholders,
        source_materials_publication_ready=not placeholders,
        scenes=scenes,
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_graph(base):
    nodes = []
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
    intensities = [0.25, 0.57, 0.9, 0.49, 0.21]

    for number in range(1, 6):
        scene = base.scenes[number - 1]
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
            intensity_delta=round(
                intensities[number] - intensities[number - 1],
                3,
            ),
            source_transition_intent=TransitionIntent.SOFT_CUT,
            cut_motivation="test",
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
        graph_hash="graph-hash",
        generated_at_utc=datetime.now(timezone.utc),
    )


class NeverAnalyzer:
    calls = 0

    def analyze(self, scene):
        self.calls += 1
        raise AssertionError("placeholder scenes must never invoke ffmpeg analyzer")


class FakeAnalyzer:
    def __init__(self, blur_by_scene):
        self.blur_by_scene = blur_by_scene
        self.calls = 0

    def analyze(self, scene):
        self.calls += 1
        blur = self.blur_by_scene[scene.scene_number]
        return RepresentativeFrameMetrics(
            sample_time_s=scene.source_start_s,
            blur_metric=blur,
            y_min=4,
            y_max=180,
            y_avg=42,
            sat_avg=35,
            luma_span=176,
            ffmpeg_binary="fake-ffmpeg",
        )


def test_placeholders_are_not_scorable_and_never_analyzed():
    base = make_base(placeholders=True)
    analyzer = NeverAnalyzer()
    result = ShotQualityScorer(analyzer=analyzer).build(
        ShotQualityRequest(
            video_base=base,
            story_graph=make_graph(base),
        )
    )

    assert result.scene_count == 5
    assert result.scored_count == 0
    assert result.not_scorable_count == 5
    assert result.analysis_failed_count == 0
    assert result.ffmpeg_frames_analyzed == 0
    assert result.mean_score is None
    assert analyzer.calls == 0
    assert all(
        scene.status == ShotQualityStatus.NOT_SCORABLE
        for scene in result.scenes
    )


def test_selected_sources_are_scored_one_frame_each(tmp_path):
    paths = {}
    for number in range(1, 6):
        path = tmp_path / f"scene-{number}.jpg"
        path.write_bytes(b"fixture")
        paths[number] = path

    base = make_base(placeholders=False, source_paths=paths)
    analyzer = FakeAnalyzer(
        {1: 0.1, 2: 0.2, 3: 0.3, 4: 0.4, 5: 0.5}
    )
    result = ShotQualityScorer(analyzer=analyzer).build(
        ShotQualityRequest(
            video_base=base,
            story_graph=make_graph(base),
        )
    )

    assert result.scored_count == 5
    assert result.ffmpeg_frames_analyzed == 5
    assert analyzer.calls == 5
    assert all(
        scene.status == ShotQualityStatus.SCORED
        for scene in result.scenes
    )
    assert result.scenes[0].components.sharpness_relative == 1.0
    assert result.scenes[-1].components.sharpness_relative == 0.0


def test_equal_blur_values_use_neutral_relative_sharpness(tmp_path):
    paths = {}
    for number in range(1, 6):
        path = tmp_path / f"scene-{number}.jpg"
        path.write_bytes(b"fixture")
        paths[number] = path

    base = make_base(placeholders=False, source_paths=paths)
    analyzer = FakeAnalyzer({number: 0.25 for number in range(1, 6)})
    result = ShotQualityScorer(analyzer=analyzer).build(
        ShotQualityRequest(
            video_base=base,
            story_graph=make_graph(base),
        )
    )

    assert all(
        scene.components.sharpness_relative == 0.5
        for scene in result.scenes
    )


def test_quality_hash_is_deterministic_for_same_inputs(tmp_path):
    paths = {}
    for number in range(1, 6):
        path = tmp_path / f"scene-{number}.jpg"
        path.write_bytes(b"fixture")
        paths[number] = path

    base = make_base(placeholders=False, source_paths=paths)
    graph = make_graph(base)

    first = ShotQualityScorer(
        analyzer=FakeAnalyzer({n: n / 10 for n in range(1, 6)})
    ).build(ShotQualityRequest(video_base=base, story_graph=graph))

    second = ShotQualityScorer(
        analyzer=FakeAnalyzer({n: n / 10 for n in range(1, 6)})
    ).build(ShotQualityRequest(video_base=base, story_graph=graph))

    assert first.quality_hash == second.quality_hash


def test_context_mismatch_is_rejected():
    base = make_base(placeholders=True)
    graph = make_graph(base)
    graph.source_plan_context_hash = "wrong"

    with pytest.raises(ShotQualityError):
        ShotQualityScorer(analyzer=NeverAnalyzer()).build(
            ShotQualityRequest(
                video_base=base,
                story_graph=graph,
            )
        )


def test_ffmpeg_metadata_parser_extracts_required_values():
    text = """
    [Parsed_metadata_3] lavfi.blur=0.1234567
    [Parsed_metadata_3] lavfi.signalstats.YMIN=3
    [Parsed_metadata_3] lavfi.signalstats.YMAX=201
    [Parsed_metadata_3] lavfi.signalstats.YAVG=42.5
    [Parsed_metadata_3] lavfi.signalstats.SATAVG=31.25
    """
    parsed = FFmpegFrameDiagnostics._parse_metadata(text)

    assert parsed["lavfi.blur"] == pytest.approx(0.1234567)
    assert parsed["lavfi.signalstats.YMIN"] == pytest.approx(3)
    assert parsed["lavfi.signalstats.YMAX"] == pytest.approx(201)
    assert parsed["lavfi.signalstats.YAVG"] == pytest.approx(42.5)
    assert parsed["lavfi.signalstats.SATAVG"] == pytest.approx(31.25)


def test_f9_guardrails_remain_false():
    base = make_base(placeholders=True)
    result = ShotQualityScorer(analyzer=NeverAnalyzer()).build(
        ShotQualityRequest(
            video_base=base,
            story_graph=make_graph(base),
        )
    )

    assert result.uses_llm is False
    assert result.gpu_required is False
    assert result.renders_video is False
    assert result.searches_material is False
    assert result.best_moment_search_triggered is False
    assert result.tracking_triggered is False
    assert result.smartfocal_triggered is False
    assert result.auto_publication is False
