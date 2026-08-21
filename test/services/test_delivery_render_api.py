from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.delivery_render as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).get("/api/v1/delivery-render/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["master"] == "2160x3840@30"
    assert data["social"] == "1080x1920@30"
    assert data["source_strategy"] == "ORIGINAL_SOURCE_RERENDER"


def test_invalid_request_422():
    app = FastAPI()
    app.include_router(controller.router)
    response = TestClient(app).post("/api/v1/delivery-render/plan", json={})
    assert response.status_code == 422
