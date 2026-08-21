from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.smart_reframing as controller


def client():
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_contract():
    response = client().get("/api/v1/smart-reframing/health")

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["version"] == "smart-reframing-v0.1"
    assert data["reframing_phase"] is True
    assert data["deterministic"] is True
    assert data["target"] == "1080x1920"
    assert data["smartfocal_foundation_reused"] is True
    assert data["smartfocal_fallback_contract_used"] is True
    assert data["dynamic_tracking"] is True
    assert data["uses_llm"] is False
    assert data["gpu_required"] is False
    assert data["renders_video"] is False
    assert data["changes_fit_mode"] is False
    assert data["tracking_reexecuted"] is False
    assert data["smartfocal_analyzer_invocations"] == 0
    assert data["auto_publication"] is False


def test_invalid_request_returns_422():
    response = client().post(
        "/api/v1/smart-reframing/plan",
        json={},
    )
    assert response.status_code == 422
