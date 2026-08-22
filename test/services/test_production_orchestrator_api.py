from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.production_orchestrator as controller


def test_health():
    app=FastAPI(); app.include_router(controller.router)
    data=TestClient(app).get("/api/v1/production-orchestrator/health").json()["data"]
    assert data["reuses_existing_pipeline"] is True
    assert data["auto_publication"] is False
