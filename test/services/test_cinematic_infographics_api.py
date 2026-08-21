from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.cinematic_infographics as controller


def client():
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_contract():
    response = client().get("/api/v1/cinematic-infographics/health")
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["version"] == "cinematic-infographics-v0.1"
    assert data["planning_only"] is True
    assert data["plan_claims_only"] is True
    assert data["fact_ids_preserved"] is True
    assert data["scientific_status_preserved"] is True
    assert data["external_data_added"] is False
    assert data["invented_numbers"] is False
    assert data["invented_charts"] is False
