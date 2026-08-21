import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.models.astronomy import (
    AstronomyBody,
    AstronomyContextRequest,
    ObserverContext,
    ScientificStatus,
)
from app.models.astronomy_director import (
    AstronomyDirectorRequest,
    AstronomyVideoPlanDraft,
    GenerationOrigin,
    NarrativeAct,
)
from app.services.astronomy_core import build_astronomy_context
from app.services.astronomy_director import (
    SOURCE_PRIORITY,
    build_grounding_packet,
    generate_astronomy_video_plan,
)


class FakeAdapter:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0
        self.schemas = []

    def available_models(self):
        return ["fake-local"]

    def resolve_model(self, requested):
        return requested or "fake-local"

    def generate_json(self, *, model, prompt, temperature, schema):
        del model, prompt, temperature
        self.schemas.append(schema)
        output = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        if isinstance(output, str):
            return output
        return json.dumps(output, ensure_ascii=False)


@pytest.fixture
def astronomy_request():
    return AstronomyContextRequest(
        observer=ObserverContext(
            latitude_deg=41.6523,
            longitude_deg=-4.7245,
            elevation_m=698,
            timezone="Europe/Madrid",
        ),
        moment=datetime(
            2026,
            8,
            21,
            22,
            0,
            tzinfo=ZoneInfo("Europe/Madrid"),
        ),
        bodies=[AstronomyBody.SUN, AstronomyBody.MOON, AstronomyBody.JUPITER],
        event_window_days=14,
        include_eclipses=False,
    )


def make_request(astronomy_request, fallback=True):
    return AstronomyDirectorRequest(
        subject="La Luna y Júpiter esta noche",
        astronomy=astronomy_request,
        target_duration_seconds=50,
        scene_count=5,
        model="fake-local",
        allow_fallback=fallback,
    )


def valid_payload(astronomy_request):
    context = build_astronomy_context(astronomy_request)
    packet = build_grounding_packet(context)
    fact_ids = [fact.fact_id for fact in packet.facts]
    scenes = []
    for index, act in enumerate(NarrativeAct, start=1):
        fact_id = fact_ids[index % len(fact_ids)]
        scenes.append(
            {
                "scene_number": index,
                "act": act.value,
                "duration_seconds": 8,
                "narration": f"Narración científica {index}",
                "visual_requirement": "Visual astronómico real y específico",
                "astronomy_objects": ["moon"],
                "shot_type": "telephoto",
                "material_keywords": ["Moon", "night sky"],
                "source_priority": [],
                "transition": "corte limpio",
                "claims": [
                    {
                        "statement": "Dato grounded",
                        "fact_ids": [fact_id],
                        "scientific_status": "HECHO_VERIFICADO",
                    }
                ],
                "ai_recreation_allowed": False,
                "scientific_status": "HECHO_VERIFICADO",
            }
        )
    return {
        "subject": "normalizado",
        "language": "es-ES",
        "audience": "general",
        "hook": "Un cielo real abre la historia",
        "scientific_context_summary": "Contexto grounded",
        "narrative_arc": [act.value for act in NarrativeAct],
        "scenes": scenes,
        "epilogue": "El cielo continúa",
        "external_research_required": False,
        "research_questions": [],
    }


def test_grounding_is_deterministic(astronomy_request):
    context = build_astronomy_context(astronomy_request)
    first = build_grounding_packet(context)
    second = build_grounding_packet(context)
    assert first.context_hash == second.context_hash
    ids = [fact.fact_id for fact in first.facts]
    assert len(ids) == len(set(ids))
    assert "moon:phase_name" in ids


def test_valid_plan_uses_schema_and_is_normalized(astronomy_request):
    adapter = FakeAdapter([valid_payload(astronomy_request)])
    plan = generate_astronomy_video_plan(
        make_request(astronomy_request),
        adapter=adapter,
    )
    assert plan.generation_origin == GenerationOrigin.LLM_VALIDATED
    assert plan.total_duration_seconds == 50
    assert plan.requires_human_review is True
    assert plan.approved_for_publication is False
    assert [scene.act for scene in plan.scenes] == list(NarrativeAct)
    assert all(scene.source_priority == SOURCE_PRIORITY for scene in plan.scenes)
    assert adapter.schemas[0] == AstronomyVideoPlanDraft.model_json_schema()


def test_repair_path(astronomy_request):
    adapter = FakeAdapter(["not-json", valid_payload(astronomy_request)])
    plan = generate_astronomy_video_plan(
        make_request(astronomy_request),
        adapter=adapter,
    )
    assert adapter.calls == 2
    assert plan.generation_origin == GenerationOrigin.LLM_REPAIRED


def test_unknown_fact_triggers_repair(astronomy_request):
    bad = valid_payload(astronomy_request)
    bad["scenes"][0]["claims"][0]["fact_ids"] = ["invented:fact"]
    adapter = FakeAdapter([bad, valid_payload(astronomy_request)])
    plan = generate_astronomy_video_plan(
        make_request(astronomy_request),
        adapter=adapter,
    )
    assert plan.generation_origin == GenerationOrigin.LLM_REPAIRED


def test_fallback_after_two_invalid_outputs(astronomy_request):
    adapter = FakeAdapter(["bad-1", "bad-2"])
    plan = generate_astronomy_video_plan(
        make_request(astronomy_request),
        adapter=adapter,
    )
    assert plan.generation_origin == GenerationOrigin.DETERMINISTIC_FALLBACK
    assert plan.total_duration_seconds == 50
    assert all(
        scene.scientific_status == ScientificStatus.INFERENCIA for scene in plan.scenes
    )


def test_no_fallback_raises(astronomy_request):
    adapter = FakeAdapter(["bad-1", "bad-2"])
    with pytest.raises(Exception):
        generate_astronomy_video_plan(
            make_request(astronomy_request, fallback=False),
            adapter=adapter,
        )


def test_research_gate_requires_questions():
    with pytest.raises(Exception):
        AstronomyVideoPlanDraft(
            subject="Tema válido",
            hook="Hook",
            scientific_context_summary="Contexto",
            narrative_arc=list(NarrativeAct),
            scenes=[],
            epilogue="Cierre",
            external_research_required=True,
            research_questions=[],
        )
