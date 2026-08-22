from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.evidence_recommendation_gate as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/evidence-recommendation-gate/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["association_only_recommendations"] is False
    assert data["updates_director_policy"] is False
    assert data["auto_apply"] is False


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/evidence-recommendation-gate/plan", json={})
    assert response.status_code == 422
