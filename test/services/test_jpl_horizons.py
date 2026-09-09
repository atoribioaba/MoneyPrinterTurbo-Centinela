import hashlib
from datetime import UTC, datetime

import pytest

import app.services.centinela.jpl_horizons as horizons
from app.models.astronomy import ObserverContext
from app.models.small_body import SmallBodyObserverRequest
from app.services.centinela.jpl_horizons import (
    HORIZONS_DOCUMENTED_API_VERSION,
    build_horizons_observer_query,
    fetch_horizons_observer_result,
    parse_horizons_observer_response,
)


def _request() -> SmallBodyObserverRequest:
    return SmallBodyObserverRequest(
        target_command="DES=2023 A3;",
        observer=ObserverContext(
            latitude_deg=41.6523,
            longitude_deg=-4.7245,
            elevation_m=700.0,
            timezone="Europe/Madrid",
        ),
        observed_at=datetime(2026, 9, 8, 22, 15, 30, tzinfo=UTC),
    )


def _result_text(
    *,
    rows: list[str] | None = None,
    header: str | None = None,
) -> str:
    data_rows = rows or [
        "2026-Sep-08 22:15:30, 123.456, -12.345, 210.123, 25.500, 5.8, 82.0,"
    ]
    header = header or (
        "Date__(UT)__HR:MN:SC.fff, R.A.__(ICRF)__deg, DEC_(ICRF)_deg, "
        "Azi_(a-app), Elev_(a-app), APmag, Illu%,"
    )
    return "\n".join(
        [
            "*******************************************************************************",
            "Target body name: C/2023 A3 (Tsuchinshan-ATLAS) {source: JPL}",
            "*******************************************************************************",
            header,
            "$$SOE",
            *data_rows,
            "$$EOE",
            "*******************************************************************************",
        ]
    )


def _payload(*, result_text: str | None = None) -> dict:
    return {
        "signature": {
            "source": "NASA/JPL Horizons API",
            "version": HORIZONS_DOCUMENTED_API_VERSION,
        },
        "result": result_text or _result_text(),
    }


def test_horizons_query_is_topocentric_reproducible_and_airless():
    plan = build_horizons_observer_query(_request())

    assert plan.endpoint.startswith("https://ssd.jpl.nasa.gov/")
    assert plan.params["EPHEM_TYPE"] == "'OBSERVER'"
    assert plan.params["CENTER"] == "'coord@399'"
    assert plan.params["COORD_TYPE"] == "'GEODETIC'"
    assert "-4.72450000,41.65230000,0.700000" in plan.params["SITE_COORD"]
    assert plan.params["TIME_TYPE"] == "'UT'"
    assert plan.params["APPARENT"] == "'AIRLESS'"
    assert plan.params["CSV_FORMAT"] == "'YES'"
    assert plan.params["QUANTITIES"] == "'2,4,8,9,10,13,47'"
    assert "fair-use" in plan.source_note


def test_horizons_response_is_version_time_checked_parsed_and_sha_bound():
    result_text = _result_text()
    result = parse_horizons_observer_response(
        _payload(result_text=result_text),
        _request(),
        retrieved_at_utc=datetime(2026, 9, 8, 22, 16, tzinfo=UTC),
    )

    assert result.target_name == "C/2023 A3 (Tsuchinshan-ATLAS)"
    assert result.columns["Elev_(a-app)"] == "25.500"
    assert result.columns["APmag"] == "5.8"
    assert result.provenance.api_version == HORIZONS_DOCUMENTED_API_VERSION
    assert result.provenance.result_sha256 == hashlib.sha256(
        result_text.encode("utf-8")
    ).hexdigest()
    assert result.provenance.query_time_utc.tzinfo is not None


def test_horizons_response_rejects_row_for_different_instant():
    payload = _payload(
        result_text=_result_text(
            rows=[
                "2026-Sep-08 22:16:30, 123.456, -12.345, 210.123, 25.500, 5.8, 82.0,"
            ]
        )
    )
    with pytest.raises(ValueError, match="does not match requested TLIST instant"):
        parse_horizons_observer_response(
            payload,
            _request(),
            retrieved_at_utc=datetime(2026, 9, 8, 22, 16, tzinfo=UTC),
        )


def test_horizons_response_requires_explicit_ut_date_column():
    result_text = _result_text(
        header=(
            "Timestamp, R.A.__(ICRF)__deg, DEC_(ICRF)_deg, Azi_(a-app), "
            "Elev_(a-app), APmag, Illu%,"
        )
    )
    with pytest.raises(ValueError, match="exactly one UT date column"):
        parse_horizons_observer_response(
            _payload(result_text=result_text),
            _request(),
            retrieved_at_utc=datetime(2026, 9, 8, 22, 16, tzinfo=UTC),
        )


def test_horizons_fetch_uses_one_allowlisted_bounded_request(monkeypatch):
    calls = []

    def fake_fetch(url, **kwargs):
        calls.append((url, kwargs))
        return _payload()

    monkeypatch.setattr(horizons, "fetch_json_https", fake_fetch)
    result = fetch_horizons_observer_result(
        _request(),
        retrieved_at_utc=datetime(2026, 9, 8, 22, 16, tzinfo=UTC),
    )

    assert result.target_name.startswith("C/2023 A3")
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url.startswith("https://ssd.jpl.nasa.gov/api/horizons.api?")
    assert kwargs["allowed_hosts"] == {"ssd.jpl.nasa.gov"}
    assert kwargs["max_bytes"] == 4_000_000


def test_horizons_response_rejects_unreviewed_api_version_by_default():
    payload = {
        "signature": {"source": "NASA/JPL Horizons API", "version": "9.9"},
        "result": _result_text(),
    }
    with pytest.raises(ValueError, match="unreviewed Horizons API version"):
        parse_horizons_observer_response(
            payload,
            _request(),
            retrieved_at_utc=datetime(2026, 9, 8, 22, 16, tzinfo=UTC),
        )


def test_horizons_single_tlist_contract_rejects_multiple_rows():
    payload = {
        "signature": {
            "source": "NASA/JPL Horizons API",
            "version": HORIZONS_DOCUMENTED_API_VERSION,
        },
        "result": _result_text(
            rows=[
                "2026-Sep-08 22:15:30, 1, 2, 3, 4, 5, 6,",
                "2026-Sep-08 22:16:30, 1, 2, 3, 4, 5, 6,",
            ]
        ),
    }
    with pytest.raises(ValueError, match="exactly one observer data row"):
        parse_horizons_observer_response(
            payload,
            _request(),
            retrieved_at_utc=datetime(2026, 9, 8, 22, 16, tzinfo=UTC),
        )


def test_horizons_error_payload_fails_closed_without_parsing_result():
    with pytest.raises(ValueError, match="error response"):
        parse_horizons_observer_response(
            {
                "signature": {
                    "source": "NASA/JPL Horizons API",
                    "version": HORIZONS_DOCUMENTED_API_VERSION,
                },
                "error": "ambiguous target",
                "result": _result_text(),
            },
            _request(),
            retrieved_at_utc=datetime(2026, 9, 8, 22, 16, tzinfo=UTC),
        )


def test_horizons_request_requires_timezone_aware_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        SmallBodyObserverRequest(
            target_command="1;",
            observer=ObserverContext(latitude_deg=0, longitude_deg=0, timezone="UTC"),
            observed_at=datetime(2026, 9, 8, 22, 0),
        )


def test_horizons_target_command_rejects_control_characters():
    with pytest.raises(ValueError, match="control characters"):
        SmallBodyObserverRequest(
            target_command="Apophis;\nMAKE_EPHEM='NO'",
            observer=ObserverContext(latitude_deg=0, longitude_deg=0, timezone="UTC"),
            observed_at=datetime(2026, 9, 8, 22, 0, tzinfo=UTC),
        )
