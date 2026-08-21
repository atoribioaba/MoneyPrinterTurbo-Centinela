from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.subtitle_intelligence as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/subtitle-intelligence/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["version"] == "subtitle-intelligence-v0.1"
    assert data["timestamp_priority"] == "NATIVE_TTS_BOUNDARIES_FIRST"
    assert data["whisper_triggered"] is False


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/subtitle-intelligence/plan", json={})
    assert response.status_code == 422
