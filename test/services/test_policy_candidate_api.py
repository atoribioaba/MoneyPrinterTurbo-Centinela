from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.policy_candidate as controller
def test_health():
    app=FastAPI(); app.include_router(controller.router); data=TestClient(app).get("/api/v1/policy-candidate/health").json()["data"]; assert data["inferred_bindings"] is False and data["activates_policy"] is False
def test_invalid_422():
    app=FastAPI(); app.include_router(controller.router); assert TestClient(app).post("/api/v1/policy-candidate/plan",json={}).status_code==422
