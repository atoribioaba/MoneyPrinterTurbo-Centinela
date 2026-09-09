from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import astronomy as ae

from app.models.astronomy import ObserverContext, ScientificStatus
from app.models.sky_planning import (
    FixedSkyTarget,
    LandscapeWindowPlan,
    LandscapeWindowRequest,
    LandscapeWindowSample,
    MeteorShowerDefinition,
    MeteorWindowPlan,
    MeteorWindowRequest,
    MeteorWindowSample,
)
from app.services.astronomy_core import ENGINE_SOURCE_ID
from app.services.centinela.horizon import horizon_altitude_deg
from app.services.centinela.observation_intelligence import angular_separation_deg
from app.services.centinela.sky_geometry import fixed_j2000_local_position


def _to_ae_time(moment: datetime) -> ae.Time:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("sky-window planning requires timezone-aware datetimes")
    utc = moment.astimezone(UTC)
    seconds = utc.second + utc.microsecond / 1_000_000.0
    return ae.Time.Make(utc.year, utc.month, utc.day, utc.hour, utc.minute, seconds)


def _observer(context: ObserverContext) -> ae.Observer:
    return ae.Observer(
        context.latitude_deg,
        context.longitude_deg,
        context.elevation_m,
    )


def _body_snapshot(
    body: ae.Body,
    observer_context: ObserverContext,
    moment: datetime,
) -> tuple[float, float, float, float]:
    engine_time = _to_ae_time(moment)
    observer = _observer(observer_context)
    eqj = ae.Equator(body, engine_time, observer, False, True)
    eqd = ae.Equator(body, engine_time, observer, True, True)
    horizon = ae.Horizon(
        engine_time,
        observer,
        eqd.ra,
        eqd.dec,
        ae.Refraction.Normal,
    )
    illuminated = 1.0
    if body != ae.Body.Sun:
        illuminated = float(ae.Illumination(body, engine_time).phase_fraction)
    return eqj.ra, eqj.dec, horizon.altitude, illuminated


def _sample_times(start: datetime, end: datetime, step_minutes: int) -> list[datetime]:
    step = timedelta(minutes=step_minutes)
    samples: list[datetime] = []
    current = start
    while current <= end:
        samples.append(current)
        current += step
    if samples[-1] != end:
        samples.append(end)
    return samples


def _darkness_factor(sun_altitude_deg: float) -> float:
    if sun_altitude_deg <= -18.0:
        return 1.0
    if sun_altitude_deg >= -6.0:
        return 0.0
    return (-6.0 - sun_altitude_deg) / 12.0


def _moon_factor(
    moon_altitude_deg: float,
    moon_illumination_fraction: float,
    separation_deg: float,
) -> float:
    if moon_altitude_deg <= 0.0:
        return 1.0
    proximity = max(0.0, (120.0 - separation_deg) / 120.0)
    return max(0.0, 1.0 - moon_illumination_fraction * proximity)


def _source_union(*groups: list[str]) -> list[str]:
    values: set[str] = {ENGINE_SOURCE_ID}
    for group in groups:
        values.update(item for item in group if item)
    return sorted(values)


def _drifted_radiant(shower: MeteorShowerDefinition, moment: datetime) -> FixedSkyTarget:
    target = shower.radiant
    if shower.radiant_epoch_utc is None:
        return target

    delta_days = (moment - shower.radiant_epoch_utc).total_seconds() / 86400.0
    ra_deg = target.right_ascension_hours_j2000 * 15.0
    dec_deg = target.declination_deg_j2000
    if shower.radiant_drift_ra_deg_per_day is not None:
        ra_deg += shower.radiant_drift_ra_deg_per_day * delta_days
    if shower.radiant_drift_dec_deg_per_day is not None:
        dec_deg += shower.radiant_drift_dec_deg_per_day * delta_days
    if not -90.0 <= dec_deg <= 90.0:
        raise ValueError("meteor radiant drift produced invalid declination")

    return target.model_copy(
        update={
            "right_ascension_hours_j2000": (ra_deg % 360.0) / 15.0,
            "declination_deg_j2000": dec_deg,
        }
    )


def _shower_active(shower: MeteorShowerDefinition, moment: datetime) -> bool:
    if shower.activity_start_utc is not None and moment < shower.activity_start_utc:
        return False
    if shower.activity_end_utc is not None and moment > shower.activity_end_utc:
        return False
    return True


def plan_meteor_window(request: MeteorWindowRequest) -> MeteorWindowPlan:
    samples: list[MeteorWindowSample] = []

    for moment in _sample_times(request.start_utc, request.end_utc, request.step_minutes):
        radiant = _drifted_radiant(request.shower, moment)
        radiant_position = fixed_j2000_local_position(radiant, request.observer, moment)
        moon_ra, moon_dec, moon_alt, moon_illumination = _body_snapshot(
            ae.Body.Moon,
            request.observer,
            moment,
        )
        _, _, sun_alt, _ = _body_snapshot(ae.Body.Sun, request.observer, moment)
        separation = angular_separation_deg(
            radiant.right_ascension_hours_j2000,
            radiant.declination_deg_j2000,
            moon_ra,
            moon_dec,
        )
        active = _shower_active(request.shower, moment)
        radiant_factor = max(
            0.0,
            math.sin(math.radians(radiant_position.altitude_airless_deg)),
        )
        geometry_score = 100.0 * radiant_factor
        geometry_score *= _darkness_factor(sun_alt)
        geometry_score *= _moon_factor(moon_alt, moon_illumination, separation)
        if not active:
            geometry_score = 0.0

        samples.append(
            MeteorWindowSample(
                observed_at=moment,
                shower_active=active,
                radiant_position=radiant_position,
                sun_altitude_deg=sun_alt,
                moon_altitude_deg=moon_alt,
                moon_illumination_fraction=moon_illumination,
                moon_radiant_separation_deg=separation,
                geometry_score=round(max(0.0, min(100.0, geometry_score)), 6),
                source_ids=_source_union(request.shower.source_ids, radiant.source_ids),
            )
        )

    eligible = [sample for sample in samples if sample.geometry_score > 0.0]
    best = max(eligible, key=lambda item: item.geometry_score) if eligible else None
    return MeteorWindowPlan(
        shower_id=request.shower.shower_id,
        samples=samples,
        best_sample=best,
        expected_observed_rate=None,
        source_ids=_source_union(
            request.shower.source_ids,
            request.shower.radiant.source_ids,
        ),
        scientific_status=ScientificStatus.INFERENCIA,
    )


def plan_landscape_window(request: LandscapeWindowRequest) -> LandscapeWindowPlan:
    samples: list[LandscapeWindowSample] = []
    horizon_sources = (
        request.horizon_profile.source_ids if request.horizon_profile is not None else []
    )

    for moment in _sample_times(request.start_utc, request.end_utc, request.step_minutes):
        target_position = fixed_j2000_local_position(request.target, request.observer, moment)
        moon_ra, moon_dec, moon_alt, moon_illumination = _body_snapshot(
            ae.Body.Moon,
            request.observer,
            moment,
        )
        _, _, sun_alt, _ = _body_snapshot(ae.Body.Sun, request.observer, moment)
        separation = angular_separation_deg(
            request.target.right_ascension_hours_j2000,
            request.target.declination_deg_j2000,
            moon_ra,
            moon_dec,
        )

        local_horizon = None
        if request.horizon_profile is not None:
            local_horizon = horizon_altitude_deg(
                request.horizon_profile,
                target_position.azimuth_deg,
            )

        blockers: list[str] = []
        if target_position.altitude_apparent_deg < request.minimum_target_altitude_deg:
            blockers.append("TARGET_ALTITUDE_BELOW_THRESHOLD")
        if (
            local_horizon is not None
            and target_position.altitude_apparent_deg <= local_horizon
        ):
            blockers.append("LOCAL_HORIZON_BLOCKED")
        if sun_alt > request.maximum_sun_altitude_deg:
            blockers.append("SUN_TOO_HIGH")
        if (
            request.minimum_moon_separation_deg is not None
            and moon_alt > 0.0
            and separation < request.minimum_moon_separation_deg
        ):
            blockers.append("MOON_TOO_CLOSE")

        altitude_factor = max(
            0.0,
            math.sin(math.radians(target_position.altitude_airless_deg)),
        )
        score = 100.0 * altitude_factor
        score *= _darkness_factor(sun_alt)
        score *= _moon_factor(moon_alt, moon_illumination, separation)
        if blockers:
            score = 0.0

        samples.append(
            LandscapeWindowSample(
                observed_at=moment,
                target_position=target_position,
                sun_altitude_deg=sun_alt,
                moon_altitude_deg=moon_alt,
                moon_illumination_fraction=moon_illumination,
                moon_target_separation_deg=separation,
                local_horizon_altitude_deg=local_horizon,
                eligible=not blockers,
                blockers=sorted(blockers),
                geometry_score=round(max(0.0, min(100.0, score)), 6),
                source_ids=_source_union(request.target.source_ids, horizon_sources),
            )
        )

    eligible = [sample for sample in samples if sample.eligible]
    best = max(eligible, key=lambda item: item.geometry_score) if eligible else None
    return LandscapeWindowPlan(
        target_id=request.target.target_id,
        samples=samples,
        best_sample=best,
        source_ids=_source_union(request.target.source_ids, horizon_sources),
        scientific_status=ScientificStatus.INFERENCIA,
    )
