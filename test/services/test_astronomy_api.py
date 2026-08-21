from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.v1.astronomy import (
    router,
)


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_astronomy_health_endpoint():
    response = _client().get(
        "/api/v1/astronomy/health"
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == 200

    data = payload["data"]

    assert data["status"] == "ok"

    assert (
        data["engine_version"]
        == "2.1.19"
    )

    assert data["cpu_only"] is True

    assert (
        data[
            "network_required_at_runtime"
        ]
        is False
    )


def test_astronomy_context_endpoint():
    response = _client().post(
        "/api/v1/astronomy/context",
        json={
            "observer": {
                "latitude_deg":
                    41.6523,

                "longitude_deg":
                    -4.7245,

                "elevation_m":
                    698,

                "timezone":
                    "Europe/Madrid",

                "name":
                    "API test fixture",
            },

            "moment":
                "2026-08-21T20:00:00+02:00",

            "bodies": [
                "sun",
                "moon",
                "jupiter",
            ],

            "event_window_days":
                10,

            "include_eclipses":
                False,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == 200

    data = payload["data"]

    assert (
        data["engine_version"]
        == "2.1.19"
    )

    assert len(
        data["bodies"]
    ) == 3

    assert (
        data["scientific_status"]
        == "HECHO_VERIFICADO"
    )

    assert data["moon"]

    assert (
        data["moon"][
            "apparent_angular_diameter_deg"
        ]
        > 0
    )

    assert data["twilight"]
    assert data["sources"]
    assert data["claims"]

    assert (
        data[
            "primary_source_verification_required_for_publication"
        ]
        is True
    )


def test_bad_timezone_returns_422():
    response = _client().post(
        "/api/v1/astronomy/context",
        json={
            "observer": {
                "latitude_deg": 41.0,
                "longitude_deg": -4.0,
                "timezone": "Wrong/Timezone",
            },
            "moment":
                "2026-08-21T20:00:00+02:00",
        },
    )

    assert response.status_code == 422


def test_naive_datetime_returns_422():
    response = _client().post(
        "/api/v1/astronomy/context",
        json={
            "observer": {
                "latitude_deg": 41.0,
                "longitude_deg": -4.0,
                "timezone": "Europe/Madrid",
            },
            "moment":
                "2026-08-21T20:00:00",
        },
    )

    assert response.status_code == 422
