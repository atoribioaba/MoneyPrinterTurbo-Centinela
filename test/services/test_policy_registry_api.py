from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.policy_registry as controller
def test_health():
    app=FastAPI()
    app.include_router(controller.router)
    d=TestClient(app).get("/api/v1/policy-registry/health").json()["data"]
    assert d["immutable_registry"] is True and d["activates_policy"] is False
def test_invalid_422():
    app=FastAPI()
    app.include_router(controller.router)
    assert TestClient(app).post("/api/v1/policy-registry/plan",json={}).status_code==422
