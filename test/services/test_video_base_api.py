from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.video_base as controller


def client():
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_contract():
    response = client().get("/api/v1/video-base/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["resolution"] == "1080x1920"
    assert data["fps"] == 30
    assert data["audio"] is False
    assert data["material_selection_authority"] == "MaterialSelectionPlan"
    assert data["material_search_triggered"] is False
    assert data["smartfocal_auto_triggered"] is False
    assert data["semantic_matcher_triggered"] is False
    assert data["wangp_triggered"] is False
    assert data["auto_publication"] is False


def test_invalid_plan_returns_422():
    response = client().post("/api/v1/video-base/plan", json={"plan": {}})
    assert response.status_code == 422
