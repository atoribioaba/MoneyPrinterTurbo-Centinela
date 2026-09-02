from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.models.astronomy import AstronomyBody, ObserverContext
from app.services.centinela import event_calendar as calendar_module
from app.services.centinela.event_calendar import (
    AstronomyEngineEventSource,
    EventCalendarService,
    RawCalendarEvent,
)


class FakeSource:
    def __init__(self, events=()):
        self.events = tuple(events)
        self.calls: list[tuple[datetime, datetime]] = []

    def events_between(self, observer, start_utc, end_utc):
        self.calls.append((start_utc, end_utc))
        return tuple(
            item for item in self.events if start_utc <= item.time_utc < end_utc
        )


def _new_york_observer() -> ObserverContext:
    return ObserverContext(
        latitude_deg=40.7128,
        longitude_deg=-74.0060,
        elevation_m=10.0,
        timezone="America/New_York",
        name="New York observer",
    )


def test_today_uses_observer_timezone_but_display_remains_official_madrid_time() -> None:
    source = FakeSource(
        (
            RawCalendarEvent(
                event_type="inside-new-york-day",
                label_es="Evento",
                time_utc=datetime(2026, 9, 2, 2, 0, tzinfo=UTC),
                body="moon",
            ),
        )
    )
    service = EventCalendarService(_new_york_observer(), source=source)

    events = service.get_events_today(
        datetime(2026, 9, 1, 23, 30, tzinfo=ZoneInfo("America/New_York"))
    )

    start_utc, end_utc = source.calls[-1]
    assert start_utc == datetime(2026, 9, 1, 4, 0, tzinfo=UTC)
    assert end_utc == datetime(2026, 9, 2, 4, 0, tzinfo=UTC)
    assert [item.event_type for item in events] == ["inside-new-york-day"]
    event = events[0]
    assert event.details["observer_local_time"]["timezone"] == "America/New_York"
    assert event.details["official_madrid_time"]["timezone"] == "Europe/Madrid"
    assert event.time_local.tzinfo == ZoneInfo("Europe/Madrid")


def test_this_month_uses_observer_timezone_at_month_boundary() -> None:
    source = FakeSource()
    service = EventCalendarService(_new_york_observer(), source=source)

    service.get_events_this_month(
        datetime(2026, 9, 15, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    )

    start_utc, end_utc = source.calls[-1]
    assert start_utc == datetime(2026, 9, 1, 4, 0, tzinfo=UTC)
    assert end_utc == datetime(2026, 10, 1, 4, 0, tzinfo=UTC)


def test_apparent_conjunction_search_refines_true_angular_minimum(monkeypatch) -> None:
    source = AstronomyEngineEventSource(base_event_builder=lambda *args, **kwargs: [])
    start = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    expected = datetime(2026, 9, 2, 3, 0, tzinfo=UTC)

    monkeypatch.setattr(
        calendar_module,
        "_APPARENT_CONJUNCTION_BODIES",
        (
            (AstronomyBody.MOON, object()),
            (AstronomyBody.JUPITER, object()),
        ),
    )

    def fake_state(cls, observer, left_body, right_body, moment):
        hours = (moment - expected).total_seconds() / 3600.0
        separation = 0.25 + (hours / 12.0) ** 2
        return {
            "separation_deg": separation,
            "left": {
                "right_ascension_hours": 1.0,
                "declination_deg": 2.0,
                "altitude_deg": 30.0,
                "azimuth_deg": 100.0,
                "above_horizon": True,
            },
            "right": {
                "right_ascension_hours": 1.1,
                "declination_deg": 2.1,
                "altitude_deg": 35.0,
                "azimuth_deg": 110.0,
                "above_horizon": True,
            },
        }

    monkeypatch.setattr(
        AstronomyEngineEventSource,
        "_apparent_pair_state",
        classmethod(fake_state),
    )

    events = source._apparent_conjunction_events(
        _new_york_observer(),
        start,
        datetime(2026, 9, 4, 0, 0, tzinfo=UTC),
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "apparent_conjunction"
    assert event.details["body_pair"] == ["moon", "jupiter"]
    assert abs((event.time_utc - expected).total_seconds()) < 10.0
    assert event.details["minimum_separation_deg"] == pytest.approx(0.25, abs=1e-6)
    assert event.details["both_above_horizon"] is True
    assert "topocentric apparent angular minimum" in event.details["search_method"]
