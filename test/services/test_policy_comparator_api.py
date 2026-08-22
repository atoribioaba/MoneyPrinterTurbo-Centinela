from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.policy_comparator as controller
def test_health():
    app=FastAPI(); app.include_router(controller.router); d=TestClient(app).get("/api/v1/policy-comparator/health").json()["data"]; assert d["quality_improvement_claims"] is False and d["activates_policy"] is False
def test_invalid_422():
    app=FastAPI(); app.include_router(controller.router); assert TestClient(app).post("/api/v1/policy-comparator/plan",json={}).status_code==422
