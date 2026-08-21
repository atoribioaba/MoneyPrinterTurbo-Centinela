from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.best_moment as controller


def client():
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_contract():
    response = client().get("/api/v1/best-moment/health")

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["version"] == "best-moment-v0.1"
    assert data["deterministic"] is True
    assert data["candidate_policy"] == "EQUALLY_SPACED_WINDOW_CENTERS_V01"
    assert data["scoring_profile"] == "TEMPORAL_TECHNICAL_V01"
    assert data["uses_llm"] is False
    assert data["gpu_required"] is False
    assert data["renders_video"] is False
    assert data["searches_material"] is False
    assert data["changes_material_identity"] is False
    assert data["tracking_triggered"] is False
    assert data["smartfocal_triggered"] is False
    assert data["auto_publication"] is False


def test_invalid_request_returns_422():
    response = client().post(
        "/api/v1/best-moment/detect",
        json={},
    )
    assert response.status_code == 422
