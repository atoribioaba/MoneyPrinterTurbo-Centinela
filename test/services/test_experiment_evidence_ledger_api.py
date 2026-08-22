from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.experiment_evidence_ledger as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/experiment-evidence-ledger/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["runs_experiments"] is False
    assert data["calculates_p_values"] is False


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/experiment-evidence-ledger/plan", json={})
    assert response.status_code == 422
