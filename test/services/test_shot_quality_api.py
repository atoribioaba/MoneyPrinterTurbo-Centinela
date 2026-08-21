from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.shot_quality as controller


def client():
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_contract():
    response = client().get("/api/v1/shot-quality/health")

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["version"] == "shot-quality-v0.1"
    assert data["deterministic"] is True
    assert data["technical_heuristic"] is True
    assert data["representative_frame_policy"] == "F6_SOURCE_START_SINGLE_FRAME"
    assert data["uses_llm"] is False
    assert data["gpu_required"] is False
    assert data["renders_video"] is False
    assert data["searches_material"] is False
    assert data["best_moment_search_triggered"] is False
    assert data["tracking_triggered"] is False
    assert data["smartfocal_triggered"] is False
    assert data["auto_publication"] is False


def test_invalid_request_returns_422():
    response = client().post(
        "/api/v1/shot-quality/score",
        json={},
    )
    assert response.status_code == 422
