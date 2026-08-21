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
from app.models.astronomy_motion_graphics import (
    AstronomyMotionGraphicsPlan,
    MotionGraphicsScene,
    MotionGraphicsStructuralChecks,
)
from app.services.cinematic_infographics import (
    CinematicInfographicsError,
    build_cinematic_infographics,
)


def make_inputs(status=ScientificStatus.HECHO_VERIFICADO):
    fact_ids = ["fact-1"] if status == ScientificStatus.HECHO_VERIFICADO else []
    scenes = []
    for index in range(1, 6):
        scenes.append(
            ScenePlan(
                scene_number=index,
                act=NarrativeAct.INTRODUCTION,
                duration_seconds=8,
                narration="Narration",
                visual_requirement="Visual",
                astronomy_objects=["Luna"],
                shot_type=ShotType.GRAPHIC,
                material_keywords=[],
                source_priority=[],
                transition="fade",
                claims=[
                    PlanScientificClaim(
                        statement="Claim grounded in the plan.",
                        fact_ids=fact_ids,
                        scientific_status=status,
                    )
                ],
                ai_recreation_allowed=False,
                scientific_status=status,
            )
        )
    plan = AstronomyVideoPlan(
        subject="Fixture",
        language="es-ES",
        audience="general",
        hook="Hook",
        scientific_context_summary="Context",
        narrative_arc=[NarrativeAct.INTRODUCTION],
        scenes=scenes,
        epilogue="Fin",
        context_hash="ctx-f17",
        generation_origin=GenerationOrigin.DETERMINISTIC_FALLBACK,
        model_used="fixture",
        repair_attempted=False,
        total_duration_seconds=40,
        generated_at_utc=datetime.now(timezone.utc),
    )
    graphics = AstronomyMotionGraphicsPlan(
        subject="Fixture",
        source_plan_context_hash="ctx-f17",
        source_story_graph_version="visual-story-graph-v0.1",
        source_story_graph_hash="graph-f17",
        scene_count=5,
        cue_count=0,
        object_label_count=0,
        claim_callout_count=0,
        review_required_count=0,
        scenes=[
            MotionGraphicsScene(
                scene_number=index,
                node_id=f"scene:{index}",
                cue_count=0,
                cues=[],
                review_required=False,
            )
            for index in range(1, 6)
        ],
        structural_checks=MotionGraphicsStructuralChecks(
            plan_graph_alignment=True,
            explicit_objects_only=True,
            plan_claims_only=True,
            verified_claim_fact_ids_preserved=True,
            no_invented_coordinates=True,
            no_invented_trajectories=True,
            no_invented_numeric_values=True,
            scientific_status_preserved=True,
        ),
        motion_graphics_hash="graphics-f17",
        generated_at_utc=datetime.now(timezone.utc),
    )
    return plan, graphics


def test_verified_claim_becomes_grounding_ready_but_still_requires_review():
    plan, graphics = make_inputs()
    result = build_cinematic_infographics(plan, graphics)

    assert result.verified_card_count == 5
    assert result.grounding_ready_count == 5
    assert result.human_review_required_count == 5
    assert result.scenes[0].cards[0].fact_ids == ["fact-1"]
    assert result.scenes[0].cards[0].human_review_required is True


def test_unverified_claim_requires_review():
    plan, graphics = make_inputs(ScientificStatus.NO_VERIFICADO)
    result = build_cinematic_infographics(plan, graphics)

    assert result.verified_card_count == 0
    assert result.grounding_ready_count == 0
    assert result.human_review_required_count == 5


def test_status_is_preserved():
    plan, graphics = make_inputs(
        ScientificStatus.APROXIMACION_DIVULGATIVA
    )
    result = build_cinematic_infographics(plan, graphics)

    card = result.scenes[0].cards[0]
    assert (
        card.scientific_status
        == ScientificStatus.APROXIMACION_DIVULGATIVA
    )
    assert card.card_type.value == "APPROXIMATION"


def test_no_external_data_numbers_or_charts():
    plan, graphics = make_inputs()
    result = build_cinematic_infographics(plan, graphics)

    for scene in result.scenes:
        for card in scene.cards:
            assert card.source_is_plan_claim is True
            assert card.external_data_added is False
            assert card.numeric_value_invented is False
            assert card.chart_invented is False


def test_context_mismatch_is_rejected():
    plan, graphics = make_inputs()
    graphics.source_plan_context_hash = "wrong"

    with pytest.raises(CinematicInfographicsError):
        build_cinematic_infographics(plan, graphics)


def test_hash_is_deterministic():
    plan, graphics = make_inputs()
    first = build_cinematic_infographics(plan, graphics)
    second = build_cinematic_infographics(plan, graphics)
    assert first.infographics_hash == second.infographics_hash


def test_guardrails_false():
    plan, graphics = make_inputs()
    result = build_cinematic_infographics(plan, graphics)

    assert result.planning_only is True
    assert result.uses_llm is False
    assert result.gpu_required is False
    assert result.renders_infographics is False
    assert result.downloads_assets is False
    assert result.searches_web is False
    assert result.computes_astronomy is False
    assert result.auto_publication is False
