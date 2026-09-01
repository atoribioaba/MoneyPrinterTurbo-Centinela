from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.golden_e2e_certification as controller
def test_health():
    app=FastAPI()
    app.include_router(controller.router)
    d=TestClient(app).get("/api/v1/golden-e2e-certification/health").json()["data"]
    assert d["required_scenarios"]==8
    assert d["real_video_required"] is True
