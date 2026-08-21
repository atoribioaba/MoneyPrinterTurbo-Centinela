from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.astronomy_director as controller
from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import (
    AstronomyVideoPlan,
    GenerationOrigin,
    NarrativeAct,
    ScenePlan,
    ShotType,
)


def client():
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def fixture_plan():
    scenes = [
        ScenePlan(
            scene_number=index,
            act=act,
            duration_seconds=10,
            narration="Narración",
            visual_requirement="Visual real",
            astronomy_objects=[],
            shot_type=ShotType.WIDE,
            material_keywords=[],
            source_priority=[],
            transition="corte",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.INFERENCIA,
        )
        for index, act in enumerate(NarrativeAct, start=1)
    ]
    return AstronomyVideoPlan(
        subject="Tema de prueba",
        language="es-ES",
        audience="general",
        hook="Hook",
        scientific_context_summary="Contexto",
        narrative_arc=list(NarrativeAct),
        scenes=scenes,
        epilogue="Cierre",
        external_research_required=False,
        research_questions=[],
        context_hash="ABC",
        generation_origin=GenerationOrigin.LLM_VALIDATED,
        model_used="fake",
        repair_attempted=False,
        total_duration_seconds=50,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


def test_plan_endpoint(monkeypatch):
    monkeypatch.setattr(
        controller,
        "generate_astronomy_video_plan",
        lambda body: fixture_plan(),
    )
    response = client().post(
        "/api/v1/astronomy/director/plan",
        json={
            "subject": "La Luna",
            "astronomy": {
                "observer": {
                    "latitude_deg": 41.6523,
                    "longitude_deg": -4.7245,
                    "elevation_m": 698,
                    "timezone": "Europe/Madrid",
                },
                "moment": "2026-08-21T22:00:00+02:00",
                "bodies": ["sun", "moon"],
                "event_window_days": 7,
                "include_eclipses": False,
            },
            "target_duration_seconds": 50,
            "scene_count": 5,
            "backend": "ollama_local",
            "model": "fake",
            "temperature": 0.15,
            "allow_fallback": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == 200
    assert payload["data"]["approved_for_publication"] is False


def test_invalid_timezone_is_422():
    response = client().post(
        "/api/v1/astronomy/director/plan",
        json={
            "subject": "La Luna",
            "astronomy": {
                "observer": {
                    "latitude_deg": 41,
                    "longitude_deg": -4,
                    "timezone": "Wrong/Timezone",
                }
            },
            "target_duration_seconds": 50,
            "scene_count": 5,
        },
    )
    assert response.status_code == 422
