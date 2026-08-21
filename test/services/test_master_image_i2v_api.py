from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.master_image_i2v as controller


def client():
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_contract():
    response = client().get("/api/v1/master-image-i2v/health")

    assert response.status_code == 200
    data = response.json()["data"]

    assert data["version"] == "master-image-i2v-v0.1"
    assert data["planning_only"] is True
    assert data["requires_f15_backend"] is True
    assert data["target_backend_family"] == "WanGP"
    assert data["explicit_ai_approval_required"] is True
    assert data["image_only_generation"] is True
    assert data["output_visual_origin"] == "AI_GENERATED"
    assert data["output_scientific_status"] == "RECREACION_VISUAL"
    assert data["ken_burns_is_fallback"] is True
    assert data["motion_stacking"] is False
    assert data["gpu_required"] is False
    assert data["renders_video"] is False
    assert data["downloads_models"] is False
    assert data["wangp_invocations"] == 0
    assert data["auto_publication"] is False


def test_invalid_request_returns_422():
    response = client().post(
        "/api/v1/master-image-i2v/plan",
        json={},
    )
    assert response.status_code == 422
