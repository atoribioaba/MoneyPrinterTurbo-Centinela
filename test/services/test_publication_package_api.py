from fastapi import FastAPI
from fastapi.testclient import TestClient
import app.controllers.v1.publication_package as controller
def test_health():
    app=FastAPI(); app.include_router(controller.router)
    d=TestClient(app).get("/api/v1/publication-package/health").json()["data"]
    assert d["manual_publication_only"] is True
    assert d["auto_publication"] is False
