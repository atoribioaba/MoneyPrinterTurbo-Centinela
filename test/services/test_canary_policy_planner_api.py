from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.canary_policy_planner as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    data = TestClient(app).get("/api/v1/canary-policy-planner/health").json()["data"]
    assert data["max_exposure_fraction"] == 0.10
    assert data["executes_canary"] is False
    assert data["requires_human_launch"] is True


def test_invalid_422():
    app = FastAPI()
    app.include_router(controller.router)
    assert TestClient(app).post("/api/v1/canary-policy-planner/plan", json={}).status_code == 422
