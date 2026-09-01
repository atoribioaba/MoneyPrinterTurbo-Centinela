from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.policy_simulator as controller
def test_health():
    app=FastAPI()
    app.include_router(controller.router)
    d=TestClient(app).get("/api/v1/policy-simulator/health").json()["data"]
    assert d["uses_real_cinematic_director"] is True and d["renders_video"] is False
def test_invalid_422():
    app=FastAPI()
    app.include_router(controller.router)
    assert TestClient(app).post("/api/v1/policy-simulator/plan",json={}).status_code==422
