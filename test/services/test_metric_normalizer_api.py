from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.metric_normalizer as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/metric-normalizer/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["cross_platform_equivalence_assumed"] is False
    assert data["api_calls"] == 0


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/metric-normalizer/plan", json={})
    assert response.status_code == 422
