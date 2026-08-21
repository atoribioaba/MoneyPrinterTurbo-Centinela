from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.voice_studio as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/voice-studio/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["version"] == "voice-studio-v0.1"
    assert data["planning_only"] is True
    assert data["timestamp_policy"] == "TTS_NATIVE_BOUNDARIES_FIRST"


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/voice-studio/plan", json={})
    assert response.status_code == 422
