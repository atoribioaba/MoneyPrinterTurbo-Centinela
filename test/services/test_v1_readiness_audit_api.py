from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.v1_readiness_audit as controller


def test_health():
    app = FastAPI()
    app.include_router(controller.router)
    data = TestClient(app).get("/api/v1/v1-readiness-audit/health").json()["data"]

    assert data["can_authorize_freeze"] is True
    assert data["executes_freeze"] is False
