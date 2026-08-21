from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.quality_comparator as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/quality-comparator/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["executes_ab_comparison"] is False
    assert data["selects_winner"] is False


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/quality-comparator/plan", json={})
    assert response.status_code == 422
