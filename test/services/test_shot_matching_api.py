from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.shot_matching as controller

def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/shot-matching/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["version"] == "shot-matching-v0.1"
    assert data["planning_only"] is True
    assert data["uses_llm"] is False
    assert data["gpu_required"] is False
    assert data["auto_publication"] is False

def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/shot-matching/plan", json={})
    assert response.status_code == 422
