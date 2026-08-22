from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.retention_intelligence as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/retention-intelligence/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["causal_claims"] is False
    assert data["recommendations_generated"] is False


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/retention-intelligence/plan", json={})
    assert response.status_code == 422
