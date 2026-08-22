from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.analytics_import_adapter as controller
def test_health():
    app=FastAPI(); app.include_router(controller.router)
    d=TestClient(app).get("/api/v1/analytics-import-adapter/health").json()["data"]
    assert d["formats"]==["CSV","JSON"]
    assert d["network_calls"]==0
