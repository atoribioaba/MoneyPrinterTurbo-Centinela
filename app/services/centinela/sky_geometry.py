from __future__ import annotations

import math
from datetime import timezone

import astronomy as ae

from app.models.astronomy import ObserverContext, ScientificStatus
from app.models.sky_planning import (
    FixedSkyTarget,
    LocalSkyPosition,
    MeteorGeometryResult,
    MeteorShowerDefinition,
)
from app.services.centinela.observation_intelligence import airmass_from_altitude_deg


def _to_ae_time(moment):
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("sky geometry requires a timezone-aware datetime")
    utc = moment.astimezone(timezone.utc)
    seconds = utc.second + utc.microsecond / 1_000_000.0
    return ae.Time.Make(
        utc.year,
        utc.month,
        utc.day,
        utc.hour,
        utc.minute,
        seconds,
    )


def fixed_j2000_local_position(
    target: FixedSkyTarget,
    observer: ObserverContext,
    moment,
) -> LocalSkyPosition:
    """Convert a source-provenanced J2000 fixed direction to local alt/az.

    Astronomy Engine's EQJ→HOR rotation handles precession/nutation/time/orientation
    for the requested instant. The catalog direction itself remains the supplied
    J2000 value; proper motion/parallax are not invented when the source does not
    provide them.
    """
    engine_time = _to_ae_time(moment)
    engine_observer = ae.Observer(
        observer.latitude_deg,
        observer.longitude_deg,
        observer.elevation_m,
    )

    eqj = ae.Spherical(
        target.declination_deg_j2000,
        target.right_ascension_hours_j2000 * 15.0,
        1.0,
    )
    eqj_vector = ae.VectorFromSphere(eqj, engine_time)
    rotation = ae.Rotation_EQJ_HOR(engine_time, engine_observer)
    horizontal_vector = ae.RotateVector(rotation, eqj_vector)

    airless = ae.HorizonFromVector(horizontal_vector, ae.Refraction.Airless)
    apparent = ae.HorizonFromVector(horizontal_vector, ae.Refraction.Normal)

    return LocalSkyPosition(
        target_id=target.target_id,
        observed_at=moment,
        altitude_airless_deg=airless.lat,
        altitude_apparent_deg=apparent.lat,
        azimuth_deg=apparent.lon % 360.0,
        above_horizon_apparent=apparent.lat > 0.0,
        airmass=airmass_from_altitude_deg(apparent.lat),
        source_ids=target.source_ids,
        scientific_status=target.scientific_status,
    )


def meteor_shower_geometry(
    shower: MeteorShowerDefinition,
    observer: ObserverContext,
    moment,
) -> MeteorGeometryResult:
    """Return radiant geometry without converting ZHR into a fake local rate."""
    if shower.radiant.kind.value != "meteor_radiant":
        raise ValueError("meteor shower radiant target must use meteor_radiant kind")

    position = fixed_j2000_local_position(shower.radiant, observer, moment)
    elevation_factor = max(0.0, math.sin(math.radians(position.altitude_airless_deg)))

    return MeteorGeometryResult(
        shower_id=shower.shower_id,
        radiant_position=position,
        radiant_elevation_factor=elevation_factor,
        theoretical_zhr=shower.theoretical_zhr,
        expected_observed_rate=None,
        scientific_status=ScientificStatus.INFERENCIA,
    )
