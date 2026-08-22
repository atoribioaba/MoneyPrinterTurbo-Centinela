from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.rollback_decision_gate as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    data = TestClient(app).get("/api/v1/rollback-decision-gate/health").json()["data"]
    assert data["decision_automatic"] is True
    assert data["executes_rollback"] is False
    assert data["activates_policy"] is False


def test_invalid_422():
    app = FastAPI()
    app.include_router(controller.router)
    assert TestClient(app).post("/api/v1/rollback-decision-gate/plan", json={}).status_code == 422
