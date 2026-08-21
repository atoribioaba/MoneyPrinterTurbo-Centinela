from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.astronomy_motion_graphics as controller


def client():
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_contract():
    response = client().get("/api/v1/astronomy-motion-graphics/health")
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["version"] == "astronomy-motion-graphics-v0.1"
    assert data["planning_only"] is True
    assert data["explicit_objects_only"] is True
    assert data["plan_claims_only"] is True
    assert data["verified_claim_fact_ids_preserved"] is True
    assert data["invented_coordinates"] is False
    assert data["invented_trajectories"] is False
    assert data["invented_numeric_values"] is False
