from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.smart_ken_burns as controller


def client():
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_contract():
    response = client().get("/api/v1/smart-ken-burns/health")

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["version"] == "smart-ken-burns-v0.1"
    assert data["ken_burns_phase"] is True
    assert data["deterministic"] is True
    assert data["normalized_geometry"] is True
    assert data["image_only_motion"] is True
    assert data["motion_mapping"]["VERY_SLOW_PUSH"] == "PUSH_IN"
    assert data["motion_mapping"]["GENTLE_PULL_BACK"] == "PULL_BACK"
    assert data["motion_mapping"]["CONTROLLED_REVEAL"] == "CONTROLLED_REVEAL"
    assert data["uses_llm"] is False
    assert data["gpu_required"] is False
    assert data["renders_video"] is False
    assert data["tracking_reexecuted"] is False
    assert data["smartfocal_reexecuted"] is False
    assert data["reframing_reexecuted"] is False
    assert data["auto_publication"] is False


def test_invalid_request_returns_422():
    response = client().post(
        "/api/v1/smart-ken-burns/plan",
        json={},
    )
    assert response.status_code == 422
