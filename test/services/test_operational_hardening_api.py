from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.operational_hardening as controller
def test_health():
    app=FastAPI(); app.include_router(controller.router)
    d=TestClient(app).get("/api/v1/operational-hardening/health").json()["data"]
    assert d["audit_only"] is True
    assert d["resets_network"] is False
