from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.association_analyzer as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/association-analyzer/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["method"] == "SPEARMAN_RANK_CORRELATION"
    assert data["p_values_calculated"] is False
    assert data["causal_claims"] is False


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/association-analyzer/plan", json={})
    assert response.status_code == 422
