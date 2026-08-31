from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.finalization_e2e as controller
def test_health():
    app=FastAPI()
    app.include_router(controller.router)
    data=TestClient(app).get("/api/v1/finalization-e2e/health").json()["data"]
    assert data["human_review_required"] is True
    assert data["auto_publication"] is False
