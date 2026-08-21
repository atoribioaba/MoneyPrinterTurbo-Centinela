from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import (
    AstronomyVideoPlan,
    GenerationOrigin,
    NarrativeAct,
    ScenePlan,
    ShotType,
)
from app.models.cinematic_director import CinematicDirectorRequest
from app.models.material_selection import SelectionStatus
from app.models.schema import VideoFitMode
from app.models.video_base import (
    VideoBaseBlockCode,
    VideoBasePlan,
    VideoBaseRenderAction,
    VideoBaseRenderMode,
    VideoBaseScenePlan,
)
from app.models.visual_story_graph import (
    NarrativeLinkType,
    SubjectLinkType,
    VisualStoryGraphRequest,
)
from app.services.cinematic_director import CinematicDirector
from app.services.visual_story_graph import (
    VisualStoryGraphBuilder,
    VisualStoryGraphError,
)


def astronomy_plan(objects=None):
    acts = [
        NarrativeAct.INTRODUCTION,
        NarrativeAct.DEVELOPMENT,
        NarrativeAct.CLIMAX,
        NarrativeAct.RESOLUTION,
        NarrativeAct.EPILOGUE,
    ]
    shots = [
        ShotType.WIDE,
        ShotType.MEDIUM,
        ShotType.TELEPHOTO,
        ShotType.STATIC,
        ShotType.WIDE,
    ]
    objects = objects or [["Moon"]] * 5

    scenes = [
        ScenePlan(
            scene_number=index,
            act=acts[index - 1],
            duration_seconds=5,
            narration=f"Narration {index}",
            visual_requirement=f"Visual {index}",
            astronomy_objects=objects[index - 1],
            shot_type=shots[index - 1],
            material_keywords=["moon"],
            source_priority=["OWN_MEDIA"],
            transition="cut",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        )
        for index in range(1, 6)
    ]

    return AstronomyVideoPlan(
        subject="Moon test",
        hook="Hook",
        scientific_context_summary="Context",
        narrative_arc=acts,
        scenes=scenes,
        epilogue="End",
        context_hash="ctx-f8",
        generation_origin=GenerationOrigin.LLM_VALIDATED,
        model_used="test",
        repair_attempted=False,
        total_duration_seconds=25,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


def video_base_plan(plan):
    scenes = [
        VideoBaseScenePlan(
            scene_number=scene.scene_number,
            scene_key=f"ctx-f8:scene:{scene.scene_number}",
            duration_seconds=float(scene.duration_seconds),
            visual_requirement=scene.visual_requirement,
            narration=scene.narration,
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
        for scene in plan.scenes
    ]

    return VideoBasePlan(
        subject=plan.subject,
        source_plan_context_hash=plan.context_hash,
        source_selector_version="material-selection-v0.1",
        render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
        requested_codec="h264_nvenc",
        scene_count=len(scenes),
        unresolved_count=len(scenes),
        placeholder_count=len(scenes),
        clean_base_eligible=False,
        source_materials_publication_ready=False,
        scenes=scenes,
        generated_at_utc=datetime.now(timezone.utc),
    )


def request(plan=None):
    plan = plan or astronomy_plan()
    base = video_base_plan(plan)
    direction = CinematicDirector().build(
        CinematicDirectorRequest(
            plan=plan,
            video_base=base,
        )
    )
    return VisualStoryGraphRequest(
        plan=plan,
        video_base=base,
        cinematic_direction=direction,
    )


def test_builds_canonical_five_node_sequential_graph():
    graph = VisualStoryGraphBuilder().build(request())

    assert graph.node_count == 5
    assert graph.edge_count == 4
    assert graph.entry_node_id == "scene:1"
    assert graph.climax_node_id == "scene:3"
    assert graph.exit_node_id == "scene:5"
    assert graph.topological_order == [
        "scene:1",
        "scene:2",
        "scene:3",
        "scene:4",
        "scene:5",
    ]


def test_graph_hash_is_deterministic():
    builder = VisualStoryGraphBuilder()

    first = builder.build(request())
    second = builder.build(request())

    assert first.graph_hash == second.graph_hash


def test_preserves_placeholders_without_marking_execution_ready():
    graph = VisualStoryGraphBuilder().build(request())

    assert graph.placeholder_count == 5
    assert all(node.placeholder for node in graph.nodes)
    assert all(not node.execution_ready for node in graph.nodes)


def test_repeated_astronomy_object_creates_one_subject_thread():
    graph = VisualStoryGraphBuilder().build(request())

    assert len(graph.subject_threads) == 1
    thread = graph.subject_threads[0]
    assert thread.subject_key == "moon"
    assert thread.scene_numbers == [1, 2, 3, 4, 5]


def test_climax_edges_are_explicit():
    graph = VisualStoryGraphBuilder().build(request())

    assert graph.edges[1].narrative_link == NarrativeLinkType.ENTER_CLIMAX
    assert graph.edges[2].narrative_link == NarrativeLinkType.EXIT_CLIMAX


def test_subject_change_is_not_silently_hidden():
    plan = astronomy_plan(
        objects=[
            ["Moon"],
            ["Moon"],
            ["Moon"],
            ["Mars"],
            ["Mars"],
        ]
    )

    graph = VisualStoryGraphBuilder().build(request(plan))

    assert graph.edges[2].subject_link == SubjectLinkType.CHANGE
    assert "SUBJECT_THREAD_BREAK" in graph.edges[2].continuity_flags


def test_f8_guardrails_are_planning_only():
    graph = VisualStoryGraphBuilder().build(request())

    assert graph.deterministic is True
    assert graph.uses_llm is False
    assert graph.gpu_required is False
    assert graph.renders_video is False
    assert graph.searches_material is False
    assert graph.auto_publication is False


def test_context_mismatch_is_rejected():
    req = request()
    req.video_base.source_plan_context_hash = "wrong-context"

    with pytest.raises(VisualStoryGraphError):
        VisualStoryGraphBuilder().build(req)
