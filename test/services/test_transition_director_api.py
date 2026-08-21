from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.transition_director as controller

def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/transition-director/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["version"] == "transition-director-v0.1"
    assert data["planning_only"] is True
    assert data["uses_llm"] is False
    assert data["gpu_required"] is False
    assert data["auto_publication"] is False

def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/transition-director/plan", json={})
    assert response.status_code == 422
