from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.content_feature_registry as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/content-feature-registry/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stores_creative_text"] is False
    assert data["database_writes"] == 0


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/content-feature-registry/plan", json={})
    assert response.status_code == 422
