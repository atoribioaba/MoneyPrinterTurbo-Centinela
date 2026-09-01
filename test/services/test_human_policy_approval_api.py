from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.human_policy_approval as controller
def test_health():
    app=FastAPI()
    app.include_router(controller.router)
    d=TestClient(app).get("/api/v1/human-policy-approval/health").json()["data"]
    assert d["auto_approval"] is False and d["activates_policy"] is False
def test_invalid_422():
    app=FastAPI()
    app.include_router(controller.router)
    assert TestClient(app).post("/api/v1/human-policy-approval/plan",json={}).status_code==422
