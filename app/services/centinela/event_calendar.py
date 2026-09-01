from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

import astronomy as ae

from app.models.astronomy import AstronomyBody, AstronomyContextRequest, ObserverContext
from app.services.astronomy_core import ENGINE_NAME, ENGINE_SOURCE_ID, ENGINE_VERSION, build_events
from app.services.centinela.research_adapters.contracts import CanonicalScientificQuantity


@dataclass(frozen=True, slots=True)
class RawCalendarEvent:
    event_type: str
    label_es: str
    time_utc: datetime
    body: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.time_utc.tzinfo is None or self.time_utc.utcoffset() is None:
            raise ValueError("calendar event time must be timezone-aware")
        object.__setattr__(self, "time_utc", self.time_utc.astimezone(UTC))
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    event_type: str
    label_es: str
    time_utc: datetime
    time_local: datetime
    body: str | None
    details: dict[str, Any]
    canonical_quantity: CanonicalScientificQuantity

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", dict(self.details))


class CalendarEventSource(Protocol):
    def events_between(
        self,
        observer: ObserverContext,
        start_utc: datetime,
        end_utc: datetime,
    ) -> tuple[RawCalendarEvent, ...]: ...


class AstronomyEngineEventSource:
    """Pure local event source backed only by Astronomy Engine."""

    _SUPERIOR_PLANETS = (
        (AstronomyBody.MARS, ae.Body.Mars),
        (AstronomyBody.JUPITER, ae.Body.Jupiter),
        (AstronomyBody.SATURN, ae.Body.Saturn),
        (AstronomyBody.URANUS, ae.Body.Uranus),
        (AstronomyBody.NEPTUNE, ae.Body.Neptune),
    )
    _INFERIOR_PLANETS = (
        (AstronomyBody.MERCURY, ae.Body.Mercury),
        (AstronomyBody.VENUS, ae.Body.Venus),
    )

    def __init__(
        self,
        *,
        base_event_builder: Callable[..., list[Any]] = build_events,
    ) -> None:
        self._base_event_builder = base_event_builder

    @staticmethod
    def _to_engine_time(value: datetime) -> Any:
        value = value.astimezone(UTC)
        seconds = value.second + value.microsecond / 1_000_000.0
        return ae.Time.Make(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            seconds,
        )

    @staticmethod
    def _from_engine_time(value: Any) -> datetime:
        return value.Utc().astimezone(UTC)

    def _base_events(
        self,
        observer: ObserverContext,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[RawCalendarEvent]:
        elapsed_days = (end_utc - start_utc).total_seconds() / 86400.0
        search_days = max(1, min(400, int(math.ceil(elapsed_days))))
        request = AstronomyContextRequest(
            observer=observer,
            moment=start_utc,
            event_window_days=search_days,
            include_eclipses=True,
        )
        result: list[RawCalendarEvent] = []
        for event in self._base_event_builder(request, start_utc):
            result.append(
                RawCalendarEvent(
                    event_type=event.event_type.value,
                    label_es=event.label_es,
                    time_utc=event.time.utc,
                    body=None if event.body is None else event.body.value,
                    details=dict(event.details),
                )
            )
        return result

    def _relative_longitude_events(
        self,
        *,
        body_name: AstronomyBody,
        engine_body: Any,
        target_deg: float,
        event_type: str,
        label_es: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[RawCalendarEvent]:
        result: list[RawCalendarEvent] = []
        cursor = self._to_engine_time(start_utc)
        for _ in range(8):
            found = ae.SearchRelativeLongitude(engine_body, target_deg, cursor)
            event_utc = self._from_engine_time(found)
            if event_utc >= end_utc:
                break
            if event_utc >= start_utc:
                result.append(
                    RawCalendarEvent(
                        event_type=event_type,
                        label_es=label_es,
                        time_utc=event_utc,
                        body=body_name.value,
                        details={"relative_longitude_target_deg": target_deg},
                    )
                )
            cursor = self._to_engine_time(event_utc + timedelta(seconds=1))
        return result

    def _max_elongation_events(
        self,
        *,
        body_name: AstronomyBody,
        engine_body: Any,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[RawCalendarEvent]:
        result: list[RawCalendarEvent] = []
        cursor = self._to_engine_time(start_utc)
        for _ in range(12):
            found = ae.SearchMaxElongation(engine_body, cursor)
            if found is None:
                break
            event_utc = self._from_engine_time(found.time)
            if event_utc >= end_utc:
                break
            if event_utc >= start_utc:
                result.append(
                    RawCalendarEvent(
                        event_type="planet_max_elongation",
                        label_es=f"Máxima elongación de {body_name.value}",
                        time_utc=event_utc,
                        body=body_name.value,
                        details={
                            "elongation_deg": float(found.elongation),
                            "visibility": found.visibility.name.lower(),
                            "ecliptic_separation_deg": float(
                                found.ecliptic_separation
                            ),
                        },
                    )
                )
            cursor = self._to_engine_time(event_utc + timedelta(seconds=1))
        return result

    def events_between(
        self,
        observer: ObserverContext,
        start_utc: datetime,
        end_utc: datetime,
    ) -> tuple[RawCalendarEvent, ...]:
        if start_utc.tzinfo is None or end_utc.tzinfo is None:
            raise ValueError("calendar boundaries must be timezone-aware")
        start_utc = start_utc.astimezone(UTC)
        end_utc = end_utc.astimezone(UTC)
        if end_utc <= start_utc:
            raise ValueError("calendar end must be after start")

        events = self._base_events(observer, start_utc, end_utc)

        for body_name, engine_body in self._SUPERIOR_PLANETS:
            events.extend(
                self._relative_longitude_events(
                    body_name=body_name,
                    engine_body=engine_body,
                    target_deg=0.0,
                    event_type="planet_opposition",
                    label_es=f"Oposición de {body_name.value}",
                    start_utc=start_utc,
                    end_utc=end_utc,
                )
            )
            events.extend(
                self._relative_longitude_events(
                    body_name=body_name,
                    engine_body=engine_body,
                    target_deg=180.0,
                    event_type="planet_conjunction",
                    label_es=f"Conjunción de {body_name.value} con el Sol",
                    start_utc=start_utc,
                    end_utc=end_utc,
                )
            )

        for body_name, engine_body in self._INFERIOR_PLANETS:
            events.extend(
                self._relative_longitude_events(
                    body_name=body_name,
                    engine_body=engine_body,
                    target_deg=0.0,
                    event_type="planet_inferior_conjunction",
                    label_es=f"Conjunción inferior de {body_name.value}",
                    start_utc=start_utc,
                    end_utc=end_utc,
                )
            )
            events.extend(
                self._relative_longitude_events(
                    body_name=body_name,
                    engine_body=engine_body,
                    target_deg=180.0,
                    event_type="planet_superior_conjunction",
                    label_es=f"Conjunción superior de {body_name.value}",
                    start_utc=start_utc,
                    end_utc=end_utc,
                )
            )
            events.extend(
                self._max_elongation_events(
                    body_name=body_name,
                    engine_body=engine_body,
                    start_utc=start_utc,
                    end_utc=end_utc,
                )
            )

        deduplicated: dict[tuple[str, str | None, datetime], RawCalendarEvent] = {}
        for event in events:
            if start_utc <= event.time_utc < end_utc:
                deduplicated[
                    (event.event_type, event.body, event.time_utc)
                ] = event
        return tuple(
            sorted(deduplicated.values(), key=lambda item: item.time_utc)
        )


class EventCalendarService:
    """Observer-local agenda backed by deterministic local ephemeris calculations."""

    def __init__(
        self,
        observer: ObserverContext,
        *,
        source: CalendarEventSource | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.observer = observer
        self._zone = ZoneInfo(observer.timezone)
        self._source = source or AstronomyEngineEventSource()
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def _observer_key(self) -> str:
        return (
            f"lat={self.observer.latitude_deg:.8f};"
            f"lon={self.observer.longitude_deg:.8f};"
            f"elevation_m={self.observer.elevation_m:.3f};"
            f"timezone={self.observer.timezone}"
        )

    def _local_moment(self, moment: datetime | None = None) -> datetime:
        value = moment if moment is not None else self._now_provider()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("agenda moment must be timezone-aware")
        return value.astimezone(self._zone)

    def _to_calendar_event(self, raw: RawCalendarEvent) -> CalendarEvent:
        local_time = raw.time_utc.astimezone(self._zone)
        occurrence = raw.time_utc.isoformat()
        body_key = raw.body or "global"
        canonical = CanonicalScientificQuantity(
            subject=f"astronomy-event:{raw.event_type}:{body_key}:{occurrence}",
            quantity="event_time",
            epoch=occurrence,
            observer=self._observer_key(),
            unit="s",
            frame="UTC",
            value=raw.time_utc.timestamp(),
            uncertainty=None,
            display_precision=0,
            source=ENGINE_SOURCE_ID,
            provenance={
                "engine": ENGINE_NAME,
                "engine_version": ENGINE_VERSION,
                "event_type": raw.event_type,
                "body": raw.body,
                "observer": {
                    "latitude_deg": self.observer.latitude_deg,
                    "longitude_deg": self.observer.longitude_deg,
                    "elevation_m": self.observer.elevation_m,
                    "timezone": self.observer.timezone,
                },
                "event_details": dict(raw.details),
                "local_time": local_time.isoformat(),
                "network_required": False,
                "auto_publication": False,
            },
        )
        return CalendarEvent(
            event_type=raw.event_type,
            label_es=raw.label_es,
            time_utc=raw.time_utc,
            time_local=local_time,
            body=raw.body,
            details=dict(raw.details),
            canonical_quantity=canonical,
        )

    def get_events_between(
        self,
        start_local: datetime,
        end_local: datetime,
    ) -> tuple[CalendarEvent, ...]:
        if (
            start_local.tzinfo is None
            or start_local.utcoffset() is None
            or end_local.tzinfo is None
            or end_local.utcoffset() is None
        ):
            raise ValueError("agenda boundaries must be timezone-aware")
        start_utc = start_local.astimezone(UTC)
        end_utc = end_local.astimezone(UTC)
        if end_utc <= start_utc:
            raise ValueError("agenda end must be after start")
        raw = self._source.events_between(self.observer, start_utc, end_utc)
        return tuple(
            self._to_calendar_event(event)
            for event in raw
            if start_utc <= event.time_utc < end_utc
        )

    def get_events_today(
        self,
        moment: datetime | None = None,
    ) -> tuple[CalendarEvent, ...]:
        local = self._local_moment(moment)
        start = datetime.combine(local.date(), time.min, tzinfo=self._zone)
        end = datetime.combine(
            local.date() + timedelta(days=1),
            time.min,
            tzinfo=self._zone,
        )
        return self.get_events_between(start, end)

    def get_events_this_month(
        self,
        moment: datetime | None = None,
    ) -> tuple[CalendarEvent, ...]:
        local = self._local_moment(moment)
        start = datetime(local.year, local.month, 1, tzinfo=self._zone)
        if local.month == 12:
            end = datetime(local.year + 1, 1, 1, tzinfo=self._zone)
        else:
            end = datetime(local.year, local.month + 1, 1, tzinfo=self._zone)
        return self.get_events_between(start, end)

    def get_events_next_365_days(
        self,
        moment: datetime | None = None,
    ) -> tuple[CalendarEvent, ...]:
        local = self._local_moment(moment)
        start_utc = local.astimezone(UTC)
        end_utc = start_utc + timedelta(days=365)
        return self.get_events_between(
            start_utc.astimezone(self._zone),
            end_utc.astimezone(self._zone),
        )
