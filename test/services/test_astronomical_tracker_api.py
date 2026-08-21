from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.astronomical_tracker as controller


def client():
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_contract():
    response = client().get("/api/v1/astronomical-tracker/health")

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["version"] == "astronomical-object-tracker-v0.1"
    assert data["tracking_phase"] is True
    assert data["deterministic"] is True
    assert data["default_backend"] == "opencv_csrt"
    assert data["opencv_loaded_lazily"] is True
    assert data["dependency_mutation"] is False
    assert data["uses_llm"] is False
    assert data["gpu_required"] is False
    assert data["renders_video"] is False
    assert data["searches_material"] is False
    assert data["changes_material_identity"] is False
    assert data["best_moment_search_triggered"] is False
    assert data["smartfocal_triggered"] is False
    assert data["reframing_triggered"] is False
    assert data["auto_publication"] is False


def test_invalid_request_returns_422():
    response = client().post(
        "/api/v1/astronomical-tracker/track",
        json={},
    )
    assert response.status_code == 422
