from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.quality_gates as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/quality-gates/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["human_approval_required"] is True
    assert data["auto_publication"] is False


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/quality-gates/plan", json={})
    assert response.status_code == 422
