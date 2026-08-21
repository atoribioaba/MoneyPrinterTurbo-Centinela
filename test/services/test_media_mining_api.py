from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.media_mining as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/media-mining/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["version"] == "media-mining-v0.1"
    assert data["candidate_detector"] == "AdaptiveDetector"
    assert data["scenedetect_invocations"] == 0


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/media-mining/plan", json={})
    assert response.status_code == 422
