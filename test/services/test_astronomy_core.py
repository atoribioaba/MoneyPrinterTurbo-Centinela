from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.models.astronomy import (
    AstronomyBody,
    AstronomyContextRequest,
    AstronomyEventType,
    ObserverContext,
    ScientificStatus,
)
from app.services.astronomy_core import (
    ENGINE_VERSION,
    build_astronomy_context,
    build_body_position,
    build_moon_context,
    build_twilight_context,
    get_astronomy_health,
)


FIXED_MOMENT = datetime(
    2026,
    8,
    21,
    20,
    0,
    0,
    tzinfo=ZoneInfo(
        "Europe/Madrid"
    ),
)


@pytest.fixture
def observer():
    # Deterministic integration fixture;
    # not a production/global default.
    return ObserverContext(
        latitude_deg=41.6523,
        longitude_deg=-4.7245,
        elevation_m=698.0,
        timezone="Europe/Madrid",
        name="Valladolid test fixture",
    )


def test_engine_version_is_pinned():
    assert ENGINE_VERSION == "2.1.19"


def test_health_contract():
    health = get_astronomy_health()

    assert health.status == "ok"
    assert health.engine_version == "2.1.19"
    assert health.license == "MIT"
    assert health.cpu_only is True

    assert (
        health.network_required_at_runtime
        is False
    )

    assert len(
        health.supported_bodies
    ) == 10


def test_invalid_timezone_is_rejected():
    with pytest.raises(
        ValidationError
    ):
        ObserverContext(
            latitude_deg=40.0,
            longitude_deg=-4.0,
            timezone=(
                "This/DoesNotExist"
            ),
        )


def test_naive_moment_is_rejected(
    observer,
):
    with pytest.raises(
        ValidationError
    ):
        AstronomyContextRequest(
            observer=observer,
            moment=datetime(
                2026,
                8,
                21,
                20,
                0,
            ),
        )


def test_moon_context(
    observer,
):
    del observer

    moon = build_moon_context(
        FIXED_MOMENT
    )

    assert (
        0.0
        <= moon.phase_longitude_deg
        < 360.0
    )

    assert (
        0.0
        <= moon.phase_angle_deg
        <= 180.0
    )

    assert (
        0.0
        <= moon.illuminated_fraction
        <= 1.0
    )

    assert (
        300000
        < moon.geocentric_distance_km
        < 500000
    )

    assert (
        0.4
        < moon.apparent_angular_diameter_deg
        < 0.7
    )

    assert (
        -15.0
        <= moon.libration_latitude_deg
        <= 15.0
    )

    assert (
        -15.0
        <= moon.libration_longitude_deg
        <= 15.0
    )

    assert (
        moon.scientific_status
        == ScientificStatus
        .HECHO_VERIFICADO
    )


@pytest.mark.parametrize(
    "body",
    list(AstronomyBody),
)
def test_body_position_ranges(
    observer,
    body,
):
    item = build_body_position(
        body,
        observer,
        FIXED_MOMENT,
    )

    assert (
        0.0
        <= item.right_ascension_hours_of_date
        < 24.0
    )

    assert (
        -90.0
        <= item.declination_deg_of_date
        <= 90.0
    )

    assert (
        0.0
        <= item.right_ascension_hours_j2000
        < 24.0
    )

    assert (
        -90.0
        <= item.declination_deg_j2000
        <= 90.0
    )

    assert (
        0.0
        <= item.azimuth_deg
        < 360.0
    )

    assert (
        -90.0
        <= item.altitude_airless_deg
        <= 90.0
    )

    assert (
        -90.0
        <= item.altitude_apparent_deg
        <= 90.0
    )

    assert (
        item.topocentric_distance_au
        > 0.0
    )

    assert (
        item.geocentric_distance_au
        > 0.0
    )

    assert item.constellation_symbol
    assert item.constellation_name

    assert math.isfinite(
        item.visual_magnitude
    )

    assert (
        0.0
        <= item.illuminated_fraction
        <= 1.0
    )

    if body == AstronomyBody.SUN:
        assert (
            item.solar_elongation_deg
            is None
        )

    else:
        assert (
            0.0
            <= item.solar_elongation_deg
            <= 180.0
        )

        assert (
            0.0
            <= item.ecliptic_separation_deg
            <= 180.0
        )

        assert (
            item.elongation_visibility
            in {
                "morning",
                "evening",
            }
        )


def test_saturn_ring_tilt(
    observer,
):
    saturn = build_body_position(
        AstronomyBody.SATURN,
        observer,
        FIXED_MOMENT,
    )

    assert (
        saturn.ring_tilt_deg
        is not None
    )

    assert (
        -30.0
        <= saturn.ring_tilt_deg
        <= 30.0
    )


def test_twilight_context(
    observer,
):
    twilight = (
        build_twilight_context(
            observer,
            FIXED_MOMENT,
        )
    )

    assert twilight.next_sunrise
    assert twilight.next_sunset

    assert twilight.next_civil_dawn
    assert twilight.next_civil_dusk

    assert twilight.next_nautical_dawn
    assert twilight.next_nautical_dusk

    assert (
        twilight.next_astronomical_dawn
    )

    assert (
        twilight.next_astronomical_dusk
    )

    assert twilight.next_solar_noon

    assert (
        twilight.search_window_days
        == 7.0
    )


def test_full_context(
    observer,
):
    request = AstronomyContextRequest(
        observer=observer,
        moment=FIXED_MOMENT,
        event_window_days=35,
        include_eclipses=False,
    )

    context = build_astronomy_context(
        request
    )

    assert (
        context.engine_version
        == "2.1.19"
    )

    assert (
        len(context.bodies)
        == len(AstronomyBody)
    )

    assert context.sources
    assert context.claims

    assert (
        context
        .primary_source_verification_required_for_publication
        is True
    )

    assert (
        context.moment_local
        .utcoffset()
        .total_seconds()
        == 7200
    )

    event_types = {
        event.event_type
        for event in context.events
    }

    lunar_quarters = {
        AstronomyEventType.MOON_NEW,
        AstronomyEventType.MOON_FIRST_QUARTER,
        AstronomyEventType.MOON_FULL,
        AstronomyEventType.MOON_THIRD_QUARTER,
    }

    assert (
        len(
            [
                event
                for event
                in context.events
                if event.event_type
                in lunar_quarters
            ]
        )
        >= 4
    )

    assert (
        AstronomyEventType.MOON_PERIGEE
        in event_types
        or AstronomyEventType.MOON_APOGEE
        in event_types
    )

    # Aug 21 + 35 days contains
    # the September equinox.
    assert (
        AstronomyEventType
        .SEPTEMBER_EQUINOX
        in event_types
    )

    assert context.events == sorted(
        context.events,
        key=lambda event:
            event.time.utc,
    )


def test_subset_deduplicates_bodies(
    observer,
):
    context = build_astronomy_context(
        AstronomyContextRequest(
            observer=observer,

            moment=FIXED_MOMENT,

            bodies=[
                AstronomyBody.SUN,
                AstronomyBody.SUN,
                AstronomyBody.MOON,
            ],

            event_window_days=0,
        )
    )

    assert [
        item.body
        for item in context.bodies
    ] == [
        AstronomyBody.SUN,
        AstronomyBody.MOON,
    ]


def test_polar_observer_does_not_crash():
    observer = ObserverContext(
        latitude_deg=69.6492,
        longitude_deg=18.9553,
        elevation_m=10.0,
        timezone="Europe/Oslo",
        name="Polar test fixture",
    )

    moment = datetime(
        2026,
        6,
        21,
        12,
        0,
        tzinfo=ZoneInfo(
            "Europe/Oslo"
        ),
    )

    context = build_astronomy_context(
        AstronomyContextRequest(
            observer=observer,
            moment=moment,
            bodies=[
                AstronomyBody.SUN
            ],
            event_window_days=0,
        )
    )

    assert len(
        context.bodies
    ) == 1
