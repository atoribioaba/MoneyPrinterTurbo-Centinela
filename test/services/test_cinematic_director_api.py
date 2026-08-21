from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.cinematic_director as controller


def client():
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_contract():
    response = client().get("/api/v1/cinematic-director/health")

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["version"] == "cinematic-director-v0.1"
    assert data["deterministic"] is True
    assert data["planning_only"] is True
    assert data["uses_llm"] is False
    assert data["gpu_required"] is False
    assert data["renders_video"] is False
    assert data["searches_material"] is False
    assert data["smartfocal_triggered"] is False
    assert data["semantic_matcher_triggered"] is False
    assert data["wangp_triggered"] is False
    assert data["tts_triggered"] is False
    assert data["whisper_triggered"] is False
    assert data["auto_publication"] is False


def test_invalid_plan_returns_422():
    response = client().post(
        "/api/v1/cinematic-director/plan",
        json={},
    )
    assert response.status_code == 422
