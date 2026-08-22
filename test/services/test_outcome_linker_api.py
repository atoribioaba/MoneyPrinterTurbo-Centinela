from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.outcome_linker as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/outcome-linker/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["cross_platform_join"] is False
    assert data["database_writes"] == 0


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/outcome-linker/plan", json={})
    assert response.status_code == 422
