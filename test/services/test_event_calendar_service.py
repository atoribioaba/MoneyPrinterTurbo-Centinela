from __future__ import annotations

import math
import socket
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models.astronomy import ObserverContext
from app.services.centinela.event_calendar import (
    MADRID_TIMEZONE,
    AstronomyEngineEventSource,
    EventCalendarService,
    RawCalendarEvent,
)


MADRID = ZoneInfo(MADRID_TIMEZONE)


class FakeSource:
    def __init__(self, events: tuple[RawCalendarEvent, ...]) -> None:
        self.events = events
        self.calls: list[tuple[datetime, datetime]] = []

    def events_between(
        self,
        observer: ObserverContext,
        start_utc: datetime,
        end_utc: datetime,
    ) -> tuple[RawCalendarEvent, ...]:
        self.calls.append((start_utc, end_utc))
        return self.events


def _observer() -> ObserverContext:
    return ObserverContext(
        latitude_deg=41.6523,
        longitude_deg=-4.7245,
        elevation_m=700.0,
        timezone="Europe/Madrid",
        name="Valladolid synthetic observer",
    )


def _raw(moment: datetime, event_type: str = "synthetic") -> RawCalendarEvent:
    return RawCalendarEvent(
        event_type=event_type,
        label_es="Evento sintético",
        time_utc=moment.astimezone(UTC),
        body="moon",
        details={"fixture": "synthetic"},
    )


def test_astronomy_engine_source_generates_events_without_external_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_network(*args, **kwargs):
        raise AssertionError("external network must not be used by EventCalendarService")

    monkeypatch.setattr(socket, "create_connection", deny_network)

    source = AstronomyEngineEventSource()
    events = source.events_between(
        _observer(),
        datetime(2026, 9, 1, tzinfo=UTC),
        datetime(2026, 10, 6, tzinfo=UTC),
    )

    assert events
    assert all(event.time_utc.tzinfo is not None for event in events)
    assert any(event.event_type.startswith("moon_") for event in events)


def test_today_uses_half_open_local_midnight_boundaries() -> None:
    source = FakeSource(
        (
            _raw(datetime(2026, 9, 1, 21, 59, tzinfo=UTC), "before-midnight"),
            _raw(datetime(2026, 9, 1, 22, 0, tzinfo=UTC), "next-midnight"),
            _raw(datetime(2026, 9, 1, 22, 1, tzinfo=UTC), "after-midnight"),
        )
    )
    service = EventCalendarService(_observer(), source=source)

    events = service.get_events_today(
        datetime(2026, 9, 1, 12, 0, tzinfo=MADRID)
    )

    assert [event.event_type for event in events] == ["before-midnight"]
    start_utc, end_utc = source.calls[-1]
    assert start_utc == datetime(2026, 8, 31, 22, 0, tzinfo=UTC)
    assert end_utc == datetime(2026, 9, 1, 22, 0, tzinfo=UTC)


def test_month_filter_excludes_next_month_and_handles_year_transition() -> None:
    source = FakeSource(
        (
            _raw(datetime(2026, 12, 31, 22, 59, tzinfo=UTC), "december"),
            _raw(datetime(2026, 12, 31, 23, 0, tzinfo=UTC), "january-boundary"),
        )
    )
    service = EventCalendarService(_observer(), source=source)

    events = service.get_events_this_month(
        datetime(2026, 12, 15, 10, 0, tzinfo=MADRID)
    )

    assert [event.event_type for event in events] == ["december"]
    start_utc, end_utc = source.calls[-1]
    assert start_utc == datetime(2026, 11, 30, 23, 0, tzinfo=UTC)
    assert end_utc == datetime(2026, 12, 31, 23, 0, tzinfo=UTC)


def test_february_leap_day_is_included_and_march_boundary_is_excluded() -> None:
    source = FakeSource(
        (
            _raw(datetime(2028, 2, 29, 11, 0, tzinfo=UTC), "leap-day"),
            _raw(datetime(2028, 2, 29, 23, 0, tzinfo=UTC), "march-boundary"),
        )
    )
    service = EventCalendarService(_observer(), source=source)

    events = service.get_events_this_month(
        datetime(2028, 2, 29, 12, 0, tzinfo=MADRID)
    )

    assert [event.event_type for event in events] == ["leap-day"]


def test_next_365_days_is_exact_elapsed_window_across_dst() -> None:
    source = FakeSource(())
    service = EventCalendarService(_observer(), source=source)
    start_local = datetime(2026, 3, 28, 12, 0, tzinfo=MADRID)

    service.get_events_next_365_days(start_local)

    start_utc, end_utc = source.calls[-1]
    assert end_utc - start_utc == timedelta(days=365)


def test_calendar_event_maps_losslessly_to_canonical_scientific_quantity() -> None:
    raw = _raw(
        datetime(2026, 9, 1, 20, 30, 15, tzinfo=UTC),
        "moon_full",
    )
    source = FakeSource((raw,))
    service = EventCalendarService(_observer(), source=source)

    events = service.get_events_between(
        datetime(2026, 9, 1, 0, 0, tzinfo=MADRID),
        datetime(2026, 9, 2, 0, 0, tzinfo=MADRID),
    )

    assert len(events) == 1
    event = events[0]
    quantity = event.canonical_quantity
    assert quantity.quantity == "event_time"
    assert quantity.value == pytest.approx(raw.time_utc.timestamp())
    assert quantity.epoch == raw.time_utc.isoformat()
    assert quantity.unit == "s"
    assert quantity.frame == "UTC"
    assert quantity.source.startswith("astronomy-engine-")
    assert quantity.provenance["network_required"] is False
    assert quantity.provenance["auto_publication"] is False
    assert quantity.provenance["observer"]["latitude_deg"] == pytest.approx(41.6523)
    assert quantity.observer.endswith("official_timezone=Europe/Madrid")
    assert event.time_local == raw.time_utc.astimezone(MADRID)


def test_official_madrid_time_switches_dynamically_between_cet_and_cest() -> None:
    winter = _raw(datetime(2026, 1, 15, 12, 0, tzinfo=UTC), "winter")
    summer = _raw(datetime(2026, 7, 15, 12, 0, tzinfo=UTC), "summer")
    service = EventCalendarService(_observer(), source=FakeSource((winter, summer)))

    events = service.get_events_between(
        datetime(2026, 1, 1, 0, 0, tzinfo=MADRID),
        datetime(2026, 8, 1, 0, 0, tzinfo=MADRID),
    )

    assert len(events) == 2
    winter_event, summer_event = events

    assert winter_event.time_local.tzname() == "CET"
    assert winter_event.time_local.isoformat().endswith("+01:00")
    winter_meta = winter_event.canonical_quantity.provenance["official_madrid_time"]
    assert winter_meta == {
        "timezone": "Europe/Madrid",
        "abbreviation": "CET",
        "utc_offset": "+01:00",
        "iso8601": winter_event.time_local.isoformat(),
    }

    assert summer_event.time_local.tzname() == "CEST"
    assert summer_event.time_local.isoformat().endswith("+02:00")
    summer_meta = summer_event.canonical_quantity.provenance["official_madrid_time"]
    assert summer_meta == {
        "timezone": "Europe/Madrid",
        "abbreviation": "CEST",
        "utc_offset": "+02:00",
        "iso8601": summer_event.time_local.isoformat(),
    }


def test_canonical_payload_contains_local_visibility_celestial_region_and_global_maximum() -> None:
    raw = RawCalendarEvent(
        event_type="local_solar_eclipse",
        label_es="Eclipse solar local",
        time_utc=datetime(2024, 4, 8, 18, 43, 12, tzinfo=UTC),
        body="sun",
        details={"fixture": "2024-total-eclipse"},
    )
    service = EventCalendarService(_observer(), source=FakeSource((raw,)))

    event = service.get_events_between(
        datetime(2024, 4, 8, 0, 0, tzinfo=MADRID),
        datetime(2024, 4, 9, 0, 0, tzinfo=MADRID),
    )[0]
    provenance = event.canonical_quantity.provenance

    local = provenance["local_circumstances"]
    assert math.isfinite(local["altitude_deg"])
    assert math.isfinite(local["azimuth_deg"])
    assert local["elevation_above_horizon_deg"] == pytest.approx(local["altitude_deg"])
    assert isinstance(local["above_horizon"], bool)

    celestial = provenance["celestial_region"]
    assert math.isfinite(celestial["right_ascension_hours"])
    assert math.isfinite(celestial["declination_deg"])
    assert celestial["constellation_symbol"]
    assert celestial["constellation_name"]

    global_maximum = provenance["global_maximum"]
    assert global_maximum["status"] == "available"
    assert math.isfinite(global_maximum["latitude_deg"])
    assert math.isfinite(global_maximum["longitude_deg"])
    assert global_maximum["region_geographic"] is None
    assert global_maximum["region_status"].startswith("NO_VERIFICADO")

    assert event.details["global_maximum"] == global_maximum
    assert event.details["local_circumstances"] == local
    assert event.details["celestial_region"] == celestial
