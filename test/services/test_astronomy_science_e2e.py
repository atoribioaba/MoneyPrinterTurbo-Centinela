from __future__ import annotations

import json
import math
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.models.astronomy import ObserverContext
from app.services.centinela.event_calendar import (
    AstronomyEngineEventSource,
    EventCalendarService,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "test" / "fixtures" / "astronomy"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _observer(payload: dict) -> ObserverContext:
    return ObserverContext(**payload["observer"])


def _moment(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    return parsed


def _match_event(events, reference: dict):
    expected = _moment(reference["expected_utc"])
    candidates = [
        event
        for event in events
        if event.event_type == reference["event_type"]
        and event.body == reference["body"]
    ]
    assert candidates, reference
    return min(
        candidates,
        key=lambda event: abs((event.time_utc - expected).total_seconds()),
    )


def _assert_time_close(actual: datetime, reference: dict) -> None:
    expected = _moment(reference["expected_utc"])
    tolerance = reference["tolerance"]
    assert math.isclose(
        actual.astimezone(UTC).timestamp(),
        expected.astimezone(UTC).timestamp(),
        rel_tol=float(tolerance["relative"]),
        abs_tol=float(tolerance["absolute_seconds"]),
    ), (
        reference["event_type"],
        actual.isoformat(),
        expected.isoformat(),
    )


def _deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Science E2E must not use external network at test runtime")

    monkeypatch.setattr(socket, "create_connection", forbidden)


def _calculate_both(payload: dict):
    observer = _observer(payload)
    start_local = _moment(payload["window"]["start_local"])
    end_local = _moment(payload["window"]["end_local"])
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)

    source = AstronomyEngineEventSource(include_apparent_conjunctions=False)
    raw = source.events_between(
        observer,
        start_utc,
        end_utc,
    )
    calendar = EventCalendarService(observer, source=source).get_events_between(
        start_local,
        end_local,
    )
    return observer, raw, calendar


@pytest.mark.parametrize(
    "fixture_name",
    [
        "usno_2026_seasons.json",
        "usno_2026_moon_phases.json",
        "naoj_2026_planetary_oppositions.json",
        "naoj_2026_greatest_elongations.json",
    ],
)
def test_event_calendar_and_astronomy_engine_match_frozen_primary_controls(
    monkeypatch: pytest.MonkeyPatch,
    fixture_name: str,
) -> None:
    _deny_network(monkeypatch)
    payload = _load(fixture_name)
    observer, raw_events, calendar_events = _calculate_both(payload)

    provider = payload["control"]["provider"]
    assert provider.startswith(("U.S. Naval Observatory", "National Astronomical Observatory"))
    for reference in payload["events"]:
        raw = _match_event(raw_events, reference)
        calendar = _match_event(calendar_events, reference)
        _assert_time_close(raw.time_utc, reference)
        _assert_time_close(calendar.time_utc, reference)

        if "expected_elongation_deg" in reference:
            expected = float(reference["expected_elongation_deg"])
            tolerance = float(reference["elongation_tolerance_deg"])
            assert math.isclose(
                abs(float(raw.details["elongation_deg"])),
                expected,
                rel_tol=0.0,
                abs_tol=tolerance,
            )
            assert math.isclose(
                abs(float(calendar.details["elongation_deg"])),
                expected,
                rel_tol=0.0,
                abs_tol=tolerance,
            )

        quantity = calendar.canonical_quantity
        assert quantity.quantity == "event_time"
        assert quantity.value == pytest.approx(calendar.time_utc.timestamp())
        assert quantity.epoch == calendar.time_utc.isoformat()
        assert quantity.unit == "s"
        assert quantity.frame == "UTC"
        assert quantity.source.startswith("astronomy-engine-")
        assert quantity.provenance["observer"]["latitude_deg"] == pytest.approx(
            observer.latitude_deg
        )
        assert quantity.provenance["observer"]["longitude_deg"] == pytest.approx(
            observer.longitude_deg
        )
        assert quantity.provenance["observer"]["elevation_m"] == pytest.approx(
            observer.elevation_m
        )
        assert quantity.provenance["observer"]["timezone"] == observer.timezone
        assert quantity.provenance["network_required"] is False
        assert quantity.provenance["auto_publication"] is False


def test_local_solar_eclipse_matches_frozen_usno_topocentric_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_network(monkeypatch)
    payload = _load("usno_2024_local_solar_eclipse_texas.json")
    observer, raw_events, calendar_events = _calculate_both(payload)
    reference = payload["events"][0]

    raw = _match_event(raw_events, reference)
    calendar = _match_event(calendar_events, reference)
    _assert_time_close(raw.time_utc, reference)
    _assert_time_close(calendar.time_utc, reference)

    assert raw.details["kind"] == reference["expected_details"]["kind"]
    assert calendar.details["kind"] == reference["expected_details"]["kind"]

    quantity = calendar.canonical_quantity
    assert quantity.quantity == "event_time"
    assert quantity.value == pytest.approx(calendar.time_utc.timestamp())
    assert quantity.epoch == calendar.time_utc.isoformat()
    assert quantity.provenance["observer"] == {
        "latitude_deg": observer.latitude_deg,
        "longitude_deg": observer.longitude_deg,
        "elevation_m": observer.elevation_m,
        "timezone": observer.timezone,
    }
    assert quantity.provenance["network_required"] is False
    assert quantity.provenance["auto_publication"] is False
