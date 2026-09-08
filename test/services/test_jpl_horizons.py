from datetime import UTC, datetime

import pytest

from app.models.astronomy import ObserverContext
from app.models.small_body import SmallBodyObserverRequest
from app.services.centinela.jpl_horizons import build_horizons_observer_query


def test_horizons_query_is_topocentric_reproducible_and_airless():
    request = SmallBodyObserverRequest(
        target_command="DES=2023 A3;",
        observer=ObserverContext(
            latitude_deg=41.6523,
            longitude_deg=-4.7245,
            elevation_m=700.0,
            timezone="Europe/Madrid",
        ),
        observed_at=datetime(2026, 9, 8, 22, 15, 30, tzinfo=UTC),
    )
    plan = build_horizons_observer_query(request)

    assert plan.endpoint.startswith("https://ssd.jpl.nasa.gov/")
    assert plan.params["EPHEM_TYPE"] == "'OBSERVER'"
    assert plan.params["CENTER"] == "'coord@399'"
    assert plan.params["COORD_TYPE"] == "'GEODETIC'"
    assert "-4.72450000,41.65230000,0.700000" in plan.params["SITE_COORD"]
    assert plan.params["TIME_TYPE"] == "'UT'"
    assert plan.params["APPARENT"] == "'AIRLESS'"
    assert plan.params["CSV_FORMAT"] == "'YES'"
    assert plan.params["QUANTITIES"] == "'2,4,8,9,10,13,47'"


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
