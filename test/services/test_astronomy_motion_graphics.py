from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import (
    AstronomyVideoPlan,
    GenerationOrigin,
    NarrativeAct,
    PlanScientificClaim,
    ScenePlan,
    ShotType,
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
from app.models.cinematic_director import (
    CinematicMood,
    CinematicNarrativeRole,
    CinematicPace,
    CompositionIntent,
    MotionIntent,
    TransitionIntent,
)
from app.services.astronomy_motion_graphics import (
    AstronomyMotionGraphicsError,
    build_motion_graphics,
)


def make_plan():
    scenes = []
    for index in range(1, 6):
        scenes.append(
            ScenePlan(
                scene_number=index,
                act=NarrativeAct.INTRODUCTION,
                duration_seconds=8,
                narration="La Luna aparece.",
                visual_requirement="Luna sobre horizonte.",
                astronomy_objects=["Luna"],
                shot_type=ShotType.STATIC,
                material_keywords=["luna"],
                source_priority=["own"],
                transition="fade",
                claims=[
                    PlanScientificClaim(
                        statement="La Luna refleja luz solar.",
                        fact_ids=["fact-moon-light"],
                        scientific_status=ScientificStatus.HECHO_VERIFICADO,
                    )
                ],
                ai_recreation_allowed=False,
                scientific_status=ScientificStatus.HECHO_VERIFICADO,
            )
        )

    return AstronomyVideoPlan(
        subject="Luna",
        language="es-ES",
        audience="general",
        hook="Mira la Luna.",
        scientific_context_summary="Contexto.",
        narrative_arc=[NarrativeAct.INTRODUCTION],
        scenes=scenes,
        epilogue="Fin.",
        context_hash="ctx",
        generation_origin=GenerationOrigin.DETERMINISTIC_FALLBACK,
        model_used="fixture",
        repair_attempted=False,
        total_duration_seconds=40,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


def make_inputs():
    plan = make_plan()
    scenes = []
    for index, source in enumerate(plan.scenes, start=1):
        scenes.append(
            VisualStoryNode(
                node_id=f"scene:{index}",
                scene_number=index,
                act=NarrativeAct.INTRODUCTION,
                duration_seconds=8.0,
                narrative_role=CinematicNarrativeRole.OPENING,
                pace=CinematicPace.MEDITATIVE,
                intensity=0.3,
                mood=CinematicMood.DISCOVERY,
                composition_intent=CompositionIntent.BALANCED_OBSERVATION,
                motion_intent=MotionIntent.OBSERVE_LOCKED,
                transition_out_intent=TransitionIntent.FADE_OUT_INTENT,
                visual_requirement="Luna sobre horizonte.",
                astronomy_objects=["Luna"],
                subject_keys=["luna"],
                continuity_group="act:introduction",
                placeholder=True,
                execution_ready=False,
            )
        )
    edges = [
        VisualStoryEdge(
            edge_id=f"edge:{index}:{index + 1}",
            source_node_id=f"scene:{index}",
            target_node_id=f"scene:{index + 1}",
            source_scene_number=index,
            target_scene_number=index + 1,
            narrative_link=NarrativeLinkType.CONTINUE_ACT,
            subject_link=SubjectLinkType.CONTINUE,
            composition_link=CompositionLinkType.HOLD,
            shared_subject_keys=["luna"],
            intensity_delta=0.0,
            source_transition_intent=TransitionIntent.FADE_OUT_INTENT,
            cut_motivation="fixture sequential continuity",
        )
        for index in range(1, 5)
    ]

    graph = VisualStoryGraph(
        subject="Luna",
        source_plan_context_hash="ctx",
        source_video_base_version="video-base-v0.1",
        source_selector_version="material-selection-v0.1",
        source_cinematic_director_version="cinematic-director-v0.1",
        source_cinematic_direction_hash="dir",
        node_count=5,
        edge_count=4,
        placeholder_count=5,
        entry_node_id="scene:1",
        climax_node_id="scene:3",
        exit_node_id="scene:5",
        topological_order=[f"scene:{i}" for i in range(1, 6)],
        nodes=scenes,
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
        graph_hash="graph",
        generated_at_utc=datetime.now(timezone.utc),
    )
    return plan, graph


def test_explicit_object_creates_label():
    plan, graph = make_inputs()
    result = build_motion_graphics(plan, graph)
    assert result.object_label_count == 5
    assert all(
        cue.text == "Luna"
        for scene in result.scenes
        for cue in scene.cues
        if cue.kind.value == "OBJECT_LABEL"
    )


def test_verified_claim_preserves_fact_ids():
    plan, graph = make_inputs()
    result = build_motion_graphics(plan, graph)
    claims = [
        cue
        for scene in result.scenes
        for cue in scene.cues
        if cue.kind.value == "SCIENTIFIC_CLAIM_CALLOUT"
    ]
    assert claims
    assert claims[0].fact_ids == ["fact-moon-light"]
    assert claims[0].scientific_status == ScientificStatus.HECHO_VERIFICADO


def test_no_coordinates_trajectories_or_numbers_are_invented():
    plan, graph = make_inputs()
    result = build_motion_graphics(plan, graph)
    for scene in result.scenes:
        for cue in scene.cues:
            assert cue.object_screen_coordinates_used is False
            assert cue.trajectory_invented is False
            assert cue.numeric_value_invented is False


def test_unverified_claim_requires_review():
    plan, graph = make_inputs()
    plan.scenes[0].claims[0].scientific_status = ScientificStatus.NO_VERIFICADO
    plan.scenes[0].claims[0].fact_ids = []
    result = build_motion_graphics(plan, graph)
    assert result.scenes[0].review_required is True


def test_alignment_mismatch_is_rejected():
    plan, graph = make_inputs()
    graph.source_plan_context_hash = "wrong"
    with pytest.raises(AstronomyMotionGraphicsError):
        build_motion_graphics(plan, graph)


def test_hash_is_deterministic():
    plan, graph = make_inputs()
    first = build_motion_graphics(plan, graph)
    second = build_motion_graphics(plan, graph)
    assert first.motion_graphics_hash == second.motion_graphics_hash


def test_guardrails_false():
    plan, graph = make_inputs()
    result = build_motion_graphics(plan, graph)
    assert result.planning_only is True
    assert result.uses_llm is False
    assert result.gpu_required is False
    assert result.renders_graphics is False
    assert result.downloads_assets is False
    assert result.searches_web is False
    assert result.tracks_objects is False
    assert result.computes_astronomy is False
    assert result.auto_publication is False
