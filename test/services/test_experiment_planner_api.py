from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.experiment_planner as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/experiment-planner/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["edits_project"] is False
    assert data["publishes_content"] is False


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/experiment-planner/plan", json={})
    assert response.status_code == 422
