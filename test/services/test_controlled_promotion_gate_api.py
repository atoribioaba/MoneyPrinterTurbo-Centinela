from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.controlled_promotion_gate as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    data = TestClient(app).get("/api/v1/controlled-promotion-gate/health").json()["data"]
    assert data["requires_human_promotion_decision"] is True
    assert data["activates_policy"] is False
    assert data["auto_apply"] is False


def test_invalid_422():
    app = FastAPI()
    app.include_router(controller.router)
    assert TestClient(app).post("/api/v1/controlled-promotion-gate/plan", json={}).status_code == 422
