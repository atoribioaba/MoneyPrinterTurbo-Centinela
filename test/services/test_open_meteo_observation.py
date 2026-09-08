from datetime import UTC, datetime

import pytest

from app.services.centinela.open_meteo_observation import (
    OPEN_METEO_ATTRIBUTION,
    OPEN_METEO_LICENSE,
    build_open_meteo_params,
    parse_open_meteo_snapshot,
    weather_snapshot_age_hours,
    weather_snapshot_is_stale,
)


def test_params_request_only_supported_meteorological_inputs():
    params = build_open_meteo_params(41.65, -4.72, forecast_days=7)
    assert params["timezone"] == "UTC"
    assert "cloud_cover_low" in params["hourly"]
    assert "dew_point_2m" in params["hourly"]
    assert "seeing" not in params["hourly"]
    assert "transparency" not in params["hourly"]


def test_parse_snapshot_preserves_forecast_semantics_and_missing_astronomy_weather():
    payload = {
        "hourly": {
            "time": ["2026-09-08T20:00", "2026-09-08T21:00"],
            "temperature_2m": [14.0, 13.0],
            "relative_humidity_2m": [50.0, 60.0],
            "dew_point_2m": [4.0, 5.0],
            "cloud_cover": [10.0, 20.0],
            "cloud_cover_low": [2.0, 4.0],
            "cloud_cover_mid": [3.0, 6.0],
            "cloud_cover_high": [5.0, 10.0],
            "wind_speed_10m": [6.0, 8.0],
            "wind_gusts_10m": [10.0, 12.0],
            "precipitation_probability": [0.0, 5.0],
        }
    }
    result = parse_open_meteo_snapshot(
        payload,
        requested_at=datetime(2026, 9, 8, 20, 40, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 8, 14, 0, tzinfo=UTC),
    )
    assert result.valid_at == datetime(2026, 9, 8, 21, 0, tzinfo=UTC)
    assert result.evidence_kind.value == "forecast"
    assert result.cloud_cover_percent == 20.0
    assert result.seeing_arcsec is None
    assert result.transparency_percent is None


def test_staleness_threshold_is_explicit_and_caller_controlled():
    payload = {"hourly": {"time": ["2026-09-08T20:00"]}}
    snapshot = parse_open_meteo_snapshot(
        payload,
        requested_at=datetime(2026, 9, 8, 20, 0, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
    )
    now = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)
    assert weather_snapshot_age_hours(snapshot, now) == 3.0
    assert weather_snapshot_is_stale(
        snapshot, now=now, max_retrieval_age_hours=2.0
    )
    assert not weather_snapshot_is_stale(
        snapshot, now=now, max_retrieval_age_hours=4.0
    )


def test_parse_rejects_naive_requested_at_and_retrieved_at():
    payload = {"hourly": {"time": ["2026-09-08T20:00"]}}
    with pytest.raises(ValueError, match="requested_at must be timezone-aware"):
        parse_open_meteo_snapshot(
            payload,
            requested_at=datetime(2026, 9, 8, 20, 0),
            retrieved_at=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="retrieved_at must be timezone-aware"):
        parse_open_meteo_snapshot(
            payload,
            requested_at=datetime(2026, 9, 8, 20, 0, tzinfo=UTC),
            retrieved_at=datetime(2026, 9, 8, 12, 0),
        )


def test_age_rejects_naive_now():
    payload = {"hourly": {"time": ["2026-09-08T20:00"]}}
    snapshot = parse_open_meteo_snapshot(
        payload,
        requested_at=datetime(2026, 9, 8, 20, 0, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        weather_snapshot_age_hours(snapshot, datetime(2026, 9, 8, 15, 0))


def test_open_meteo_attribution_contract_is_explicit():
    assert OPEN_METEO_LICENSE == "CC BY 4.0"
    assert "Open-Meteo" in OPEN_METEO_ATTRIBUTION
