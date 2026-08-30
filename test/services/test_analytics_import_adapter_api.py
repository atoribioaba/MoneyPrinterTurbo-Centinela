from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.controllers.v1.analytics_import_adapter as controller


def client() -> TestClient:
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_health_exposes_fail_closed_guardrails():
    data = client().get("/api/v1/analytics-import-adapter/health").json()["data"]

    assert data["formats"] == ["CSV", "JSON"]
    assert data["adapter_only"] is True
    assert data["network_calls"] == 0
    assert data["api_calls"] == 0
    assert data["database_writes"] == 0
    assert data["credentials_required"] is False
    assert data["uses_llm"] is False
    assert data["auto_publication"] is False


def test_parse_accepts_valid_json_without_external_side_effects():
    response = client().post(
        "/api/v1/analytics-import-adapter/parse",
        json={
            "format": "JSON",
            "payload_text": (
                '[{"platform":"YOUTUBE","content_id":"v1",'
                '"native_metric_name":"views","value":10,'
                '"value_type":"COUNT",'
                '"observed_at_utc":"2026-08-22T18:00:00Z"}]'
            ),
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "IMPORT_READY"
    assert data["observation_count"] == 1
    assert data["network_calls"] == 0
    assert data["database_writes"] == 0
    assert data["auto_publication"] is False


def test_parse_returns_422_for_invalid_import():
    response = client().post(
        "/api/v1/analytics-import-adapter/parse",
        json={"format": "JSON", "payload_text": "{bad"},
    )

    assert response.status_code == 422
    assert "invalid JSON" in response.json()["detail"]
