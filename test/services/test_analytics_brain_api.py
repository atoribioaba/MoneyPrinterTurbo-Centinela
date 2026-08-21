from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.analytics_brain as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/analytics-brain/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["storage_candidate"] == "SQLite"
    assert data["storage_writes"] == 0


def test_empty_plan():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/analytics-brain/plan", json={"observations": []})
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "WAITING_FOR_ANALYTICS_DATA"
