from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.performance_signals as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/performance-signals/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["cross_platform_ranking"] is False
    assert data["composite_score_enabled"] is False


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/performance-signals/plan", json={})
    assert response.status_code == 422
