from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.material_selection as controller


def client():
    app = FastAPI()

    app.include_router(controller.router)

    return TestClient(app)


def test_health():
    response = client().get("/api/v1/material-selection/health")

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["deterministic"] is True

    assert data["semantic_model_required"] is False

    assert data["provider_download_triggered"] is False

    assert data["auto_publication"] is False


def test_invalid_plan_returns_422():
    response = client().post(
        "/api/v1/material-selection/plan",
        json={"plan": {"subject": "invalid"}},
    )

    assert response.status_code == 422
