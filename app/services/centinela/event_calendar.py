from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from itertools import combinations
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

import astronomy as ae

from app.models.astronomy import AstronomyBody, AstronomyContextRequest, ObserverContext
from app.services.astronomy_core import (
    ENGINE_NAME,
    ENGINE_SOURCE_ID,
    ENGINE_VERSION,
    build_events,
)
from app.services.centinela.research_adapters.contracts import (
    CanonicalScientificQuantity,
)


MADRID_TIMEZONE = "Europe/Madrid"
MADRID_ZONE = ZoneInfo(MADRID_TIMEZONE)

_BODY_TO_ENGINE = {
    AstronomyBody.SUN.value: ae.Body.Sun,
    AstronomyBody.MOON.value: ae.Body.Moon,
    AstronomyBody.MERCURY.value: ae.Body.Mercury,
    AstronomyBody.VENUS.value: ae.Body.Venus,
    AstronomyBody.MARS.value: ae.Body.Mars,
    AstronomyBody.JUPITER.value: ae.Body.Jupiter,
    AstronomyBody.SATURN.value: ae.Body.Saturn,
    AstronomyBody.URANUS.value: ae.Body.Uranus,
    AstronomyBody.NEPTUNE.value: ae.Body.Neptune,
    AstronomyBody.PLUTO.value: ae.Body.Pluto,
}

# Only Moon-planet and planet-planet pairs are searched. The Sun is deliberately
# excluded because planet-Sun conjunctions already use Astronomy Engine's
# SearchRelativeLongitude primitives below.
_APPARENT_CONJUNCTION_BODIES = (
    (AstronomyBody.MOON, ae.Body.Moon),
    (AstronomyBody.MERCURY, ae.Body.Mercury),
    (AstronomyBody.VENUS, ae.Body.Venus),
    (AstronomyBody.MARS, ae.Body.Mars),
    (AstronomyBody.JUPITER, ae.Body.Jupiter),
    (AstronomyBody.SATURN, ae.Body.Saturn),
    (AstronomyBody.URANUS, ae.Body.Uranus),
    (AstronomyBody.NEPTUNE, ae.Body.Neptune),
)

_CONJUNCTION_SCAN_STEP = timedelta(hours=12)
_CONJUNCTION_REFINEMENT_SECONDS = 1.0
# A broad candidate gate prevents every synodic local minimum from being
# surfaced as a useful conjunction while still leaving the numerical minimum
# itself unconstrained. This is product-selection metadata, not measurement
# uncertainty.
_CONJUNCTION_CANDIDATE_MAX_SEPARATION_DEG = 8.0

# G-003 canonical opposition contract:
# apparent geocentric ecliptic longitude(planet) - longitude(Sun) = 180 deg.
# SearchRelativeLongitude remains useful only as a deterministic nearby seed because
# its documented geometry is heliocentric and therefore is not itself the event.
_OPPOSITION_TARGET_DEG = 180.0
_OPPOSITION_SEARCH_TOLERANCE_SECONDS = 0.1
_OPPOSITION_MAX_BRACKET_DAYS = 4.0
_OPPOSITION_SCIENTIFIC_DISPLAY_RESOLUTION_SECONDS = 60


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
        include_apparent_conjunctions: bool = True,
    ) -> None:
        self._base_event_builder = base_event_builder
        self._include_apparent_conjunctions = bool(include_apparent_conjunctions)

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

    @staticmethod
    def _ae_observer(observer: ObserverContext) -> Any:
        return ae.Observer(
            observer.latitude_deg,
            observer.longitude_deg,
            observer.elevation_m,
        )

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

    @classmethod
    def _apparent_geocentric_opposition_state(
        cls,
        engine_body: Any,
        moment: datetime,
    ) -> dict[str, float]:
        """Return geocentric apparent true-ecliptic-of-date opposition geometry."""
        event_time = cls._to_engine_time(moment)
        planet = ae.Ecliptic(ae.GeoVector(engine_body, event_time, True))
        sun = ae.Ecliptic(ae.GeoVector(ae.Body.Sun, event_time, True))
        difference = (float(planet.elon) - float(sun.elon)) % 360.0
        offset = ((difference - _OPPOSITION_TARGET_DEG + 180.0) % 360.0) - 180.0
        return {
            "planet_ecliptic_longitude_deg": float(planet.elon),
            "sun_ecliptic_longitude_deg": float(sun.elon),
            "longitude_difference_deg": difference,
            "target_offset_deg": offset,
        }

    @classmethod
    def _refine_apparent_geocentric_opposition(
        cls,
        engine_body: Any,
        seed_utc: datetime,
    ) -> tuple[datetime, dict[str, float]]:
        """Refine a heliocentric seed to the canonical geocentric apparent root."""
        bracket: tuple[datetime, datetime, float, float] | None = None
        for half_days in (1.0, 2.0, _OPPOSITION_MAX_BRACKET_DAYS):
            left = seed_utc - timedelta(days=half_days)
            right = seed_utc + timedelta(days=half_days)
            left_value = cls._apparent_geocentric_opposition_state(
                engine_body,
                left,
            )["target_offset_deg"]
            right_value = cls._apparent_geocentric_opposition_state(
                engine_body,
                right,
            )["target_offset_deg"]
            if left_value == 0.0:
                return left, cls._apparent_geocentric_opposition_state(
                    engine_body,
                    left,
                )
            if right_value == 0.0:
                return right, cls._apparent_geocentric_opposition_state(
                    engine_body,
                    right,
                )
            if left_value * right_value < 0.0:
                bracket = (left, right, left_value, right_value)
                break

        if bracket is None:
            raise RuntimeError(
                "canonical geocentric apparent opposition root was not bracketed "
                f"within +/-{_OPPOSITION_MAX_BRACKET_DAYS:g} days of the "
                "Astronomy Engine heliocentric seed"
            )

        left, right, left_value, _ = bracket
        for _ in range(80):
            if (right - left).total_seconds() <= _OPPOSITION_SEARCH_TOLERANCE_SECONDS:
                break
            midpoint = left + (right - left) / 2
            midpoint_value = cls._apparent_geocentric_opposition_state(
                engine_body,
                midpoint,
            )["target_offset_deg"]
            if midpoint_value == 0.0:
                left = midpoint
                right = midpoint
                break
            if left_value * midpoint_value <= 0.0:
                right = midpoint
            else:
                left = midpoint
                left_value = midpoint_value

        event_utc = left + (right - left) / 2
        return (
            event_utc,
            cls._apparent_geocentric_opposition_state(engine_body, event_utc),
        )

    def _opposition_events(
        self,
        *,
        body_name: AstronomyBody,
        engine_body: Any,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[RawCalendarEvent]:
        """Find canonical geocentric apparent oppositions for a superior planet."""
        result: list[RawCalendarEvent] = []
        cursor = self._to_engine_time(start_utc)
        for _ in range(8):
            # Astronomy Engine documents SearchRelativeLongitude as a heliocentric
            # planet/Earth longitude search. It is deliberately used only to find
            # a nearby deterministic seed, never as the canonical opposition time.
            seed = ae.SearchRelativeLongitude(engine_body, 0.0, cursor)
            seed_utc = self._from_engine_time(seed)
            if seed_utc > end_utc + timedelta(days=_OPPOSITION_MAX_BRACKET_DAYS):
                break

            event_utc, state = self._refine_apparent_geocentric_opposition(
                engine_body,
                seed_utc,
            )
            if event_utc >= end_utc:
                break
            if event_utc >= start_utc:
                result.append(
                    RawCalendarEvent(
                        event_type="planet_opposition",
                        label_es=f"Oposición de {body_name.value}",
                        time_utc=event_utc,
                        body=body_name.value,
                        details={
                            "opposition_definition": (
                                "geocentric apparent ecliptic longitude difference "
                                "planet-minus-Sun = 180 deg"
                            ),
                            "observer_basis": "geocenter",
                            "coordinate_basis": (
                                "geocentric apparent true ecliptic/equinox of date"
                            ),
                            "apparent": True,
                            "light_time_correction": True,
                            "aberration_correction": True,
                            "longitude_difference_target_deg": _OPPOSITION_TARGET_DEG,
                            **state,
                            "search_method": (
                                "Astronomy Engine heliocentric SearchRelativeLongitude "
                                "seed + deterministic bisection of geocentric apparent "
                                "true-ecliptic-of-date longitude difference"
                            ),
                            "computational_tolerance_seconds": (
                                _OPPOSITION_SEARCH_TOLERANCE_SECONDS
                            ),
                            "scientific_display_resolution_seconds": (
                                _OPPOSITION_SCIENTIFIC_DISPLAY_RESOLUTION_SECONDS
                            ),
                            "engine": ENGINE_NAME,
                            "engine_version": ENGINE_VERSION,
                        },
                    )
                )

            cursor = self._to_engine_time(seed_utc + timedelta(seconds=1))
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

    @staticmethod
    def _angular_separation_deg(
        left_ra_hours: float,
        left_dec_deg: float,
        right_ra_hours: float,
        right_dec_deg: float,
    ) -> float:
        left_ra = math.radians(left_ra_hours * 15.0)
        right_ra = math.radians(right_ra_hours * 15.0)
        left_dec = math.radians(left_dec_deg)
        right_dec = math.radians(right_dec_deg)
        dot = (
            math.sin(left_dec) * math.sin(right_dec)
            + math.cos(left_dec)
            * math.cos(right_dec)
            * math.cos(left_ra - right_ra)
        )
        return math.degrees(math.acos(max(-1.0, min(1.0, dot))))

    @classmethod
    def _apparent_pair_state(
        cls,
        observer: ObserverContext,
        left_body: Any,
        right_body: Any,
        moment: datetime,
    ) -> dict[str, Any]:
        """Return topocentric apparent-of-date directions and spherical separation."""
        event_time = cls._to_engine_time(moment)
        topocenter = cls._ae_observer(observer)

        def body_state(engine_body: Any) -> dict[str, Any]:
            equator = ae.Equator(
                engine_body,
                event_time,
                topocenter,
                True,
                True,
            )
            horizon = ae.Horizon(
                event_time,
                topocenter,
                equator.ra,
                equator.dec,
                ae.Refraction.Normal,
            )
            return {
                "right_ascension_hours": float(equator.ra),
                "declination_deg": float(equator.dec),
                "altitude_deg": float(horizon.altitude),
                "azimuth_deg": float(horizon.azimuth),
                "above_horizon": bool(horizon.altitude > 0.0),
            }

        left = body_state(left_body)
        right = body_state(right_body)
        separation = cls._angular_separation_deg(
            left["right_ascension_hours"],
            left["declination_deg"],
            right["right_ascension_hours"],
            right["declination_deg"],
        )
        return {
            "separation_deg": separation,
            "left": left,
            "right": right,
        }

    @classmethod
    def _refine_pair_minimum(
        cls,
        observer: ObserverContext,
        left_body: Any,
        right_body: Any,
        start: datetime,
        end: datetime,
    ) -> tuple[datetime, dict[str, Any]]:
        """Golden-section search of a bracketed apparent angular minimum."""
        if end <= start:
            raise ValueError("conjunction refinement bracket must be increasing")

        width = (end - start).total_seconds()
        phi = (1.0 + math.sqrt(5.0)) / 2.0
        left_seconds = 0.0
        right_seconds = width

        def evaluate(seconds: float) -> tuple[datetime, dict[str, Any]]:
            moment = start + timedelta(seconds=seconds)
            return moment, cls._apparent_pair_state(
                observer,
                left_body,
                right_body,
                moment,
            )

        c_seconds = right_seconds - (right_seconds - left_seconds) / phi
        d_seconds = left_seconds + (right_seconds - left_seconds) / phi
        c_moment, c_state = evaluate(c_seconds)
        d_moment, d_state = evaluate(d_seconds)

        for _ in range(80):
            if right_seconds - left_seconds <= _CONJUNCTION_REFINEMENT_SECONDS:
                break
            if c_state["separation_deg"] <= d_state["separation_deg"]:
                right_seconds = d_seconds
                d_seconds, d_moment, d_state = c_seconds, c_moment, c_state
                c_seconds = right_seconds - (right_seconds - left_seconds) / phi
                c_moment, c_state = evaluate(c_seconds)
            else:
                left_seconds = c_seconds
                c_seconds, c_moment, c_state = d_seconds, d_moment, d_state
                d_seconds = left_seconds + (right_seconds - left_seconds) / phi
                d_moment, d_state = evaluate(d_seconds)

        best_seconds = (left_seconds + right_seconds) / 2.0
        return evaluate(best_seconds)

    def _apparent_conjunction_events(
        self,
        observer: ObserverContext,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[RawCalendarEvent]:
        """Find Moon-planet and planet-planet apparent angular minima."""
        if end_utc <= start_utc:
            return []

        result: list[RawCalendarEvent] = []
        for (left_name, left_body), (right_name, right_body) in combinations(
            _APPARENT_CONJUNCTION_BODIES,
            2,
        ):
            samples: list[tuple[datetime, float]] = []
            cursor = start_utc
            while cursor < end_utc:
                state = self._apparent_pair_state(
                    observer,
                    left_body,
                    right_body,
                    cursor,
                )
                samples.append((cursor, float(state["separation_deg"])))
                cursor += _CONJUNCTION_SCAN_STEP
            if not samples or samples[-1][0] < end_utc:
                final_probe = min(end_utc, samples[-1][0] + _CONJUNCTION_SCAN_STEP)
                if final_probe > samples[-1][0]:
                    state = self._apparent_pair_state(
                        observer,
                        left_body,
                        right_body,
                        final_probe,
                    )
                    samples.append((final_probe, float(state["separation_deg"])))

            for index in range(1, len(samples) - 1):
                previous = samples[index - 1]
                current = samples[index]
                following = samples[index + 1]
                if not (
                    current[1] <= previous[1]
                    and current[1] <= following[1]
                ):
                    continue

                minimum_time, minimum = self._refine_pair_minimum(
                    observer,
                    left_body,
                    right_body,
                    previous[0],
                    following[0],
                )
                separation = float(minimum["separation_deg"])
                if separation > _CONJUNCTION_CANDIDATE_MAX_SEPARATION_DEG:
                    continue
                if not (start_utc <= minimum_time < end_utc):
                    continue

                pair = [left_name.value, right_name.value]
                details = {
                    "body_pair": pair,
                    "minimum_separation_deg": separation,
                    "left": dict(minimum["left"]),
                    "right": dict(minimum["right"]),
                    "both_above_horizon": bool(
                        minimum["left"]["above_horizon"]
                        and minimum["right"]["above_horizon"]
                    ),
                    "search_method": (
                        "topocentric apparent angular minimum; "
                        "12-hour deterministic scan + golden-section refinement"
                    ),
                    "coordinate_basis": "topocentric apparent equator/equinox of date",
                    "horizon_refraction": "normal",
                    "scan_step_seconds": _CONJUNCTION_SCAN_STEP.total_seconds(),
                    "refinement_tolerance_seconds": (
                        _CONJUNCTION_REFINEMENT_SECONDS
                    ),
                    "candidate_maximum_separation_deg": (
                        _CONJUNCTION_CANDIDATE_MAX_SEPARATION_DEG
                    ),
                    "engine": ENGINE_NAME,
                    "engine_version": ENGINE_VERSION,
                }
                result.append(
                    RawCalendarEvent(
                        event_type="apparent_conjunction",
                        label_es=(
                            f"Conjunción aparente de {left_name.value} "
                            f"y {right_name.value}"
                        ),
                        time_utc=minimum_time,
                        body=left_name.value,
                        details=details,
                    )
                )

        # A sampled flat minimum can create adjacent brackets. Collapse only
        # numerical duplicates for the same pair, never distinct events.
        result.sort(key=lambda event: event.time_utc)
        deduplicated: list[RawCalendarEvent] = []
        for event in result:
            if deduplicated:
                previous = deduplicated[-1]
                if (
                    previous.details.get("body_pair")
                    == event.details.get("body_pair")
                    and abs(
                        (event.time_utc - previous.time_utc).total_seconds()
                    )
                    <= _CONJUNCTION_SCAN_STEP.total_seconds()
                ):
                    if (
                        event.details["minimum_separation_deg"]
                        < previous.details["minimum_separation_deg"]
                    ):
                        deduplicated[-1] = event
                    continue
            deduplicated.append(event)
        return deduplicated

    def events_between(
        self,
        observer: ObserverContext,
        start_utc: datetime,
        end_utc: datetime,
    ) -> tuple[RawCalendarEvent, ...]:
        if (
            start_utc.tzinfo is None
            or start_utc.utcoffset() is None
            or end_utc.tzinfo is None
            or end_utc.utcoffset() is None
        ):
            raise ValueError("calendar boundaries must be timezone-aware")
        start_utc = start_utc.astimezone(UTC)
        end_utc = end_utc.astimezone(UTC)
        if end_utc <= start_utc:
            raise ValueError("calendar end must be after start")

        events = self._base_events(observer, start_utc, end_utc)

        for body_name, engine_body in self._SUPERIOR_PLANETS:
            events.extend(
                self._opposition_events(
                    body_name=body_name,
                    engine_body=engine_body,
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

        if self._include_apparent_conjunctions:
            events.extend(
                self._apparent_conjunction_events(
                    observer,
                    start_utc,
                    end_utc,
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
    """Observer-local agenda with separate official mainland-Spain presentation."""

    def __init__(
        self,
        observer: ObserverContext,
        *,
        source: CalendarEventSource | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.observer = observer
        self._observer_zone = ZoneInfo(observer.timezone)
        self._madrid_zone = MADRID_ZONE
        self._source = source or AstronomyEngineEventSource()
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def _observer_key(self) -> str:
        return (
            f"lat={self.observer.latitude_deg:.8f};"
            f"lon={self.observer.longitude_deg:.8f};"
            f"elevation_m={self.observer.elevation_m:.3f};"
            f"observer_timezone={self.observer.timezone};"
            f"official_timezone={MADRID_TIMEZONE}"
        )

    def _local_moment(self, moment: datetime | None = None) -> datetime:
        value = moment if moment is not None else self._now_provider()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("agenda moment must be timezone-aware")
        return value.astimezone(self._observer_zone)

    @staticmethod
    def _offset_text(value: datetime) -> str:
        compact = value.strftime("%z")
        if len(compact) != 5:
            return compact
        return f"{compact[:3]}:{compact[3:]}"

    def _time_metadata(
        self,
        time_utc: datetime,
        *,
        zone: ZoneInfo,
        timezone_name: str,
    ) -> dict[str, Any]:
        local = time_utc.astimezone(zone)
        return {
            "timezone": timezone_name,
            "abbreviation": local.tzname(),
            "utc_offset": self._offset_text(local),
            "iso8601": local.isoformat(),
        }

    def _official_time_metadata(self, time_utc: datetime) -> dict[str, Any]:
        return self._time_metadata(
            time_utc,
            zone=self._madrid_zone,
            timezone_name=MADRID_TIMEZONE,
        )

    def _observer_local_time_metadata(
        self,
        time_utc: datetime,
    ) -> dict[str, Any]:
        return self._time_metadata(
            time_utc,
            zone=self._observer_zone,
            timezone_name=self.observer.timezone,
        )

    def _ae_observer(self) -> Any:
        return ae.Observer(
            self.observer.latitude_deg,
            self.observer.longitude_deg,
            self.observer.elevation_m,
        )

    def _local_and_celestial_metadata(
        self,
        raw: RawCalendarEvent,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        engine_body = _BODY_TO_ENGINE.get(raw.body or "")
        if engine_body is None:
            unavailable = {
                "status": "not_available",
                "reason": "event has no supported Solar System body",
            }
            return unavailable, unavailable

        event_time = AstronomyEngineEventSource._to_engine_time(raw.time_utc)
        observer = self._ae_observer()

        eqd = ae.Equator(
            engine_body,
            event_time,
            observer,
            True,
            True,
        )
        horizon = ae.Horizon(
            event_time,
            observer,
            eqd.ra,
            eqd.dec,
            ae.Refraction.Normal,
        )

        eqj = ae.Equator(
            engine_body,
            event_time,
            observer,
            False,
            True,
        )
        constellation = ae.Constellation(eqj.ra, eqj.dec)

        local = {
            "observer_name": self.observer.name,
            "latitude_deg": self.observer.latitude_deg,
            "longitude_deg": self.observer.longitude_deg,
            "elevation_m": self.observer.elevation_m,
            "altitude_deg": float(horizon.altitude),
            "azimuth_deg": float(horizon.azimuth),
            "elevation_above_horizon_deg": float(horizon.altitude),
            "above_horizon": bool(horizon.altitude > 0.0),
            "refraction": "normal",
        }
        celestial = {
            "frame": "J2000",
            "right_ascension_hours": float(eqj.ra),
            "declination_deg": float(eqj.dec),
            "constellation_symbol": constellation.symbol,
            "constellation_name": constellation.name,
        }
        return local, celestial

    def _global_maximum_metadata(
        self,
        raw: RawCalendarEvent,
    ) -> dict[str, Any]:
        if raw.event_type == "local_solar_eclipse":
            start = AstronomyEngineEventSource._to_engine_time(
                raw.time_utc - timedelta(days=2)
            )
            eclipse = ae.SearchGlobalSolarEclipse(start)
            peak_utc = AstronomyEngineEventSource._from_engine_time(eclipse.peak)
            if abs((peak_utc - raw.time_utc).total_seconds()) > 3 * 86400:
                return {
                    "status": "not_matched",
                    "reason": (
                        "global eclipse search did not match local eclipse window"
                    ),
                    "region_geographic": None,
                    "region_status": "NO_VERIFICADO",
                }

            latitude_raw = getattr(eclipse, "latitude", None)
            longitude_raw = getattr(eclipse, "longitude", None)
            try:
                latitude = float(latitude_raw)
                longitude = float(longitude_raw)
            except (TypeError, ValueError):
                latitude = math.nan
                longitude = math.nan
            coordinates_defined = (
                math.isfinite(latitude) and math.isfinite(longitude)
            )
            return {
                "status": "available" if coordinates_defined else "not_defined",
                "kind": eclipse.kind.name.lower(),
                "peak_utc": peak_utc.isoformat(),
                "latitude_deg": latitude if coordinates_defined else None,
                "longitude_deg": longitude if coordinates_defined else None,
                "region_geographic": None,
                "region_status": (
                    "NO_VERIFICADO — Astronomy Engine supplies geographic "
                    "coordinates, but the local runtime has no authoritative "
                    "geographic-region/continent resolver"
                ),
                "definition_note": (
                    "Latitude/longitude represent the center of the Moon's "
                    "shadow at global peak for total/annular eclipses. They "
                    "are undefined for partial solar eclipses."
                ),
            }

        if raw.event_type == "lunar_eclipse":
            return {
                "status": "not_applicable",
                "latitude_deg": None,
                "longitude_deg": None,
                "region_geographic": None,
                "reason": (
                    "A lunar eclipse has a global peak instant but no unique "
                    "terrestrial surface point of maximum; visibility spans "
                    "the night hemisphere."
                ),
            }

        return {
            "status": "not_applicable",
            "latitude_deg": None,
            "longitude_deg": None,
            "region_geographic": None,
            "reason": (
                "this event has no scientifically defined terrestrial maximum point"
            ),
        }

    def _canonical_quantity(
        self,
        *,
        subject: str,
        quantity: str,
        epoch: str,
        unit: str,
        frame: str,
        value: float,
        display_precision: int | None,
        provenance: dict[str, Any],
    ) -> CanonicalScientificQuantity:
        return CanonicalScientificQuantity(
            subject=subject,
            quantity=quantity,
            epoch=epoch,
            observer=self._observer_key(),
            unit=unit,
            frame=frame,
            value=value,
            uncertainty=None,
            display_precision=display_precision,
            source=ENGINE_SOURCE_ID,
            provenance={
                "engine": ENGINE_NAME,
                "engine_version": ENGINE_VERSION,
                "network_required": False,
                "auto_publication": False,
                **dict(provenance),
            },
        )

    def _conjunction_quantities(
        self,
        raw: RawCalendarEvent,
        *,
        subject: str,
        occurrence: str,
    ) -> list[CanonicalScientificQuantity]:
        if raw.event_type != "apparent_conjunction":
            return []
        pair = raw.details.get("body_pair")
        left = raw.details.get("left")
        right = raw.details.get("right")
        if not (
            isinstance(pair, list)
            and len(pair) == 2
            and isinstance(left, dict)
            and isinstance(right, dict)
        ):
            return []

        provenance = {
            "event_type": raw.event_type,
            "body_pair": list(pair),
            "search_method": raw.details.get("search_method"),
        }
        quantities = [
            self._canonical_quantity(
                subject=subject,
                quantity="minimum_apparent_separation",
                epoch=occurrence,
                unit="deg",
                frame="TOPOCENTRIC_APPARENT_EQUATOR_OF_DATE",
                value=float(raw.details["minimum_separation_deg"]),
                display_precision=6,
                provenance=provenance,
            )
        ]
        for side_name, state in (("left", left), ("right", right)):
            body = str(pair[0] if side_name == "left" else pair[1])
            side_subject = f"{subject}:{body}"
            quantities.extend(
                (
                    self._canonical_quantity(
                        subject=side_subject,
                        quantity="right_ascension",
                        epoch=occurrence,
                        unit="hour",
                        frame="TOPOCENTRIC_APPARENT_EQUATOR_OF_DATE",
                        value=float(state["right_ascension_hours"]),
                        display_precision=6,
                        provenance=provenance,
                    ),
                    self._canonical_quantity(
                        subject=side_subject,
                        quantity="declination",
                        epoch=occurrence,
                        unit="deg",
                        frame="TOPOCENTRIC_APPARENT_EQUATOR_OF_DATE",
                        value=float(state["declination_deg"]),
                        display_precision=6,
                        provenance=provenance,
                    ),
                    self._canonical_quantity(
                        subject=side_subject,
                        quantity="altitude",
                        epoch=occurrence,
                        unit="deg",
                        frame="TOPOCENTRIC_HORIZON_REFRACTED",
                        value=float(state["altitude_deg"]),
                        display_precision=4,
                        provenance=provenance,
                    ),
                    self._canonical_quantity(
                        subject=side_subject,
                        quantity="azimuth",
                        epoch=occurrence,
                        unit="deg",
                        frame="TOPOCENTRIC_HORIZON_REFRACTED",
                        value=float(state["azimuth_deg"]),
                        display_precision=4,
                        provenance=provenance,
                    ),
                )
            )
        return quantities

    def _to_calendar_event(self, raw: RawCalendarEvent) -> CalendarEvent:
        official_time = raw.time_utc.astimezone(self._madrid_zone)
        occurrence = raw.time_utc.isoformat()
        body_key = raw.body or "global"
        subject = f"astronomy-event:{raw.event_type}:{body_key}:{occurrence}"

        local_circumstances, celestial_region = (
            self._local_and_celestial_metadata(raw)
        )
        global_maximum = self._global_maximum_metadata(raw)
        official_time_metadata = self._official_time_metadata(raw.time_utc)
        observer_time_metadata = self._observer_local_time_metadata(raw.time_utc)

        details = dict(raw.details)
        details.update(
            {
                "observer_local_time": observer_time_metadata,
                "official_madrid_time": official_time_metadata,
                "local_circumstances": local_circumstances,
                "global_maximum": global_maximum,
                "celestial_region": celestial_region,
            }
        )

        conjunction_quantities = self._conjunction_quantities(
            raw,
            subject=subject,
            occurrence=occurrence,
        )
        details["canonical_scientific_quantities"] = [
            item.as_dict() for item in conjunction_quantities
        ]

        canonical = self._canonical_quantity(
            subject=subject,
            quantity="event_time",
            epoch=occurrence,
            unit="s",
            frame="UTC",
            value=raw.time_utc.timestamp(),
            display_precision=0,
            provenance={
                "event_type": raw.event_type,
                "body": raw.body,
                "observer": {
                    "latitude_deg": self.observer.latitude_deg,
                    "longitude_deg": self.observer.longitude_deg,
                    "elevation_m": self.observer.elevation_m,
                    "timezone": self.observer.timezone,
                },
                "observer_local_time": observer_time_metadata,
                "official_madrid_time": official_time_metadata,
                "local_circumstances": local_circumstances,
                "global_maximum": global_maximum,
                "celestial_region": celestial_region,
                "event_details": dict(details),
            },
        )

        return CalendarEvent(
            event_type=raw.event_type,
            label_es=raw.label_es,
            time_utc=raw.time_utc,
            time_local=official_time,
            body=raw.body,
            details=details,
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
        start = datetime.combine(
            local.date(),
            time.min,
            tzinfo=self._observer_zone,
        )
        end = datetime.combine(
            local.date() + timedelta(days=1),
            time.min,
            tzinfo=self._observer_zone,
        )
        return self.get_events_between(start, end)

    def get_events_this_month(
        self,
        moment: datetime | None = None,
    ) -> tuple[CalendarEvent, ...]:
        local = self._local_moment(moment)
        start = datetime(
            local.year,
            local.month,
            1,
            tzinfo=self._observer_zone,
        )
        if local.month == 12:
            end = datetime(
                local.year + 1,
                1,
                1,
                tzinfo=self._observer_zone,
            )
        else:
            end = datetime(
                local.year,
                local.month + 1,
                1,
                tzinfo=self._observer_zone,
            )
        return self.get_events_between(start, end)

    def get_events_next_365_days(
        self,
        moment: datetime | None = None,
    ) -> tuple[CalendarEvent, ...]:
        """Return [instant, instant + 365*24h); this is not a calendar year."""
        local = self._local_moment(moment)
        start_utc = local.astimezone(UTC)
        end_utc = start_utc + timedelta(days=365)
        return self.get_events_between(
            start_utc.astimezone(self._observer_zone),
            end_utc.astimezone(self._observer_zone),
        )
