from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.video_base_e2e as controller

def test_health():
    app=FastAPI()
    app.include_router(controller.router)
    data=TestClient(app).get("/api/v1/video-base-e2e/health").json()["data"]
    assert data["verification_only"] is True
    assert data["renders_video"] is False
