from datetime import UTC, datetime

import astronomy as ae
import pytest

from app.models.astronomy import ObserverContext, ScientificStatus
from app.models.sky_planning import (
    FixedSkyTarget,
    FixedSkyTargetKind,
    MeteorShowerDefinition,
)
from app.services.centinela.sky_geometry import (
    fixed_j2000_local_position,
    meteor_shower_geometry,
)


def _engine_time(moment: datetime):
    return ae.Time.Make(
        moment.year,
        moment.month,
        moment.day,
        moment.hour,
        moment.minute,
        moment.second,
    )


def test_fixed_j2000_direction_near_local_meridian_zenith_at_equator():
    moment = datetime(2026, 9, 8, 22, 0, tzinfo=UTC)
    # Greenwich sidereal time is the RA on the local meridian at longitude 0.
    meridian_ra = ae.SiderealTime(_engine_time(moment))
    target = FixedSkyTarget(
        target_id="fixture-zenith",
        name="Fixture",
        kind=FixedSkyTargetKind.STAR,
        right_ascension_hours_j2000=meridian_ra,
        declination_deg_j2000=0.0,
        source_ids=["fixture"],
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )
    observer = ObserverContext(
        latitude_deg=0.0,
        longitude_deg=0.0,
        timezone="UTC",
    )
    result = fixed_j2000_local_position(target, observer, moment)
    # J2000->of-date precession/nutation means it need not land at exactly 90 deg.
    assert result.altitude_airless_deg > 89.0
    assert result.above_horizon_apparent is True
    assert result.airmass is not None and result.airmass < 1.01


def test_fixed_sky_requires_timezone_aware_datetime():
    target = FixedSkyTarget(
        target_id="fixture",
        name="Fixture",
        kind=FixedSkyTargetKind.OTHER,
        right_ascension_hours_j2000=10.0,
        declination_deg_j2000=20.0,
        source_ids=["fixture"],
        scientific_status=ScientificStatus.NO_VERIFICADO,
    )
    observer = ObserverContext(latitude_deg=40.0, longitude_deg=-4.0, timezone="UTC")
    with pytest.raises(ValueError, match="timezone-aware"):
        fixed_j2000_local_position(target, observer, datetime(2026, 9, 8, 22, 0))


def test_meteor_geometry_never_claims_expected_observed_rate():
    moment = datetime(2026, 9, 8, 22, 0, tzinfo=UTC)
    radiant = FixedSkyTarget(
        target_id="fixture-radiant",
        name="Fixture radiant",
        kind=FixedSkyTargetKind.METEOR_RADIANT,
        right_ascension_hours_j2000=3.0,
        declination_deg_j2000=45.0,
        source_ids=["fixture-shower-catalog"],
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )
    shower = MeteorShowerDefinition(
        shower_id="fixture-shower",
        name="Fixture shower",
        radiant=radiant,
        theoretical_zhr=100.0,
        source_ids=["fixture-shower-catalog"],
    )
    observer = ObserverContext(
        latitude_deg=41.65,
        longitude_deg=-4.72,
        timezone="Europe/Madrid",
    )
    result = meteor_shower_geometry(shower, observer, moment)
    assert 0.0 <= result.radiant_elevation_factor <= 1.0
    assert result.theoretical_zhr == 100.0
    assert result.expected_observed_rate is None
    assert "does not predict" in result.interpretation


def test_meteor_shower_rejects_non_radiant_target_kind():
    target = FixedSkyTarget(
        target_id="not-radiant",
        name="Not radiant",
        kind=FixedSkyTargetKind.STAR,
        right_ascension_hours_j2000=3.0,
        declination_deg_j2000=45.0,
        source_ids=["fixture"],
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )
    shower = MeteorShowerDefinition(
        shower_id="bad",
        name="Bad",
        radiant=target,
        source_ids=["fixture"],
    )
    observer = ObserverContext(latitude_deg=41.65, longitude_deg=-4.72, timezone="UTC")
    with pytest.raises(ValueError, match="meteor_radiant"):
        meteor_shower_geometry(shower, observer, datetime(2026, 9, 8, tzinfo=UTC))
