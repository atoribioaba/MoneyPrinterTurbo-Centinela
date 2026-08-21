from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.wangp_backend as controller


def client():
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_contract():
    response = client().get("/api/v1/wangp-backend/health")
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["version"] == "wangp-backend-v0.1"
    assert data["audit_only"] is True
    assert data["downloads_models"] is False
    assert data["modifies_wangp"] is False
    assert data["large_download_authorized"] is False
