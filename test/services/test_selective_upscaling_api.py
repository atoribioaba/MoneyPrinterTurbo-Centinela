from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.selective_upscaling as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/selective-upscaling/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["version"] == "selective-upscaling-v0.1"
    assert data["runs_upscaler"] is False
    assert data["downloads_models"] is False


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/selective-upscaling/plan", json={})
    assert response.status_code == 422
