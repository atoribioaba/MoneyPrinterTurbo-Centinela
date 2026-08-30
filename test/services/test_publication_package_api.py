from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.publication_package as controller


def client() -> TestClient:
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_exposes_publication_package_v0_2_guardrails():
    response = client().get("/api/v1/publication-package/health")
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["version"] == "publication-package-v0.2"
    assert data["planning_only"] is True
    assert data["manual_publication_only"] is True
    assert data["writes_files"] is False
    assert data["uploads_files"] is False
    assert data["network_calls"] == 0
    assert data["webhook_calls"] == 0
    assert data["auto_publication"] is False
    assert data["authorization_to_publish"] is False
    assert data["marks_published"] is False
    assert data["local_final_certification_required"] is True
