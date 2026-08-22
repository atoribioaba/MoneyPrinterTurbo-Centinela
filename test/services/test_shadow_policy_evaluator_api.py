from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.shadow_policy_evaluator as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    data = TestClient(app).get("/api/v1/shadow-policy-evaluator/health").json()["data"]
    assert data["shadow_only"] is True
    assert data["runtime_effect"] is False
    assert data["activates_policy"] is False


def test_invalid_422():
    app = FastAPI()
    app.include_router(controller.router)
    assert TestClient(app).post("/api/v1/shadow-policy-evaluator/plan", json={}).status_code == 422
