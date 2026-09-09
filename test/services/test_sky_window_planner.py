from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.models.astronomy import ObserverContext, ScientificStatus
from app.models.sky_planning import (
    FixedSkyTarget,
    FixedSkyTargetKind,
    LandscapeWindowRequest,
    MeteorShowerDefinition,
    MeteorWindowRequest,
)
from app.services.centinela.sky_window_planner import (
    plan_landscape_window,
    plan_meteor_window,
)


OBSERVER = ObserverContext(
    latitude_deg=41.6523,
    longitude_deg=-4.7245,
    elevation_m=698.0,
    timezone="Europe/Madrid",
    name="Valladolid",
)


def _radiant() -> FixedSkyTarget:
    return FixedSkyTarget(
        target_id="meteor-radiant-test",
        name="Radiant test",
        kind=FixedSkyTargetKind.METEOR_RADIANT,
        right_ascension_hours_j2000=3.1,
        declination_deg_j2000=58.0,
        source_ids=["iau_mdc_fixture"],
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )


def _shower() -> MeteorShowerDefinition:
    peak = datetime(2026, 8, 13, 2, 0, tzinfo=UTC)
    return MeteorShowerDefinition(
        shower_id="test-shower",
        name="Test shower",
        radiant=_radiant(),
        peak_time_utc=peak,
        activity_start_utc=peak - timedelta(days=2),
        activity_end_utc=peak + timedelta(days=2),
        radiant_epoch_utc=peak,
        radiant_drift_ra_deg_per_day=0.8,
        radiant_drift_dec_deg_per_day=0.1,
        theoretical_zhr=100.0,
        population_index=2.2,
        catalog_status="ESTABLISHED_FIXTURE",
        source_ids=["iau_mdc_fixture"],
    )


def test_meteor_window_never_turns_zhr_into_predicted_local_rate():
    start = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
    plan = plan_meteor_window(
        MeteorWindowRequest(
            shower=_shower(),
            observer=OBSERVER,
            start_utc=start,
            end_utc=start + timedelta(hours=8),
            step_minutes=30,
        )
    )

    assert plan.expected_observed_rate is None
    assert plan.samples
    assert all(0.0 <= sample.geometry_score <= 100.0 for sample in plan.samples)
    assert all(sample.source_ids for sample in plan.samples)
    assert "predicted observed meteor count" in plan.interpretation
    assert plan.scientific_status == ScientificStatus.INFERENCIA


def test_meteor_samples_outside_declared_activity_are_zero_scored():
    start = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)
    plan = plan_meteor_window(
        MeteorWindowRequest(
            shower=_shower(),
            observer=OBSERVER,
            start_utc=start,
            end_utc=start + timedelta(hours=2),
            step_minutes=30,
        )
    )

    assert all(sample.shower_active is False for sample in plan.samples)
    assert all(sample.geometry_score == 0.0 for sample in plan.samples)
    assert plan.best_sample is None


def test_meteor_radiant_drift_requires_an_explicit_epoch():
    with pytest.raises(ValidationError, match="radiant drift requires radiant_epoch_utc"):
        MeteorShowerDefinition(
            shower_id="bad",
            name="Bad",
            radiant=_radiant(),
            radiant_drift_ra_deg_per_day=1.0,
            source_ids=["iau_mdc_fixture"],
        )


def test_meteor_activity_interval_must_be_ordered():
    moment = datetime(2026, 8, 13, 0, 0, tzinfo=UTC)
    with pytest.raises(ValidationError, match="activity start must precede"):
        MeteorShowerDefinition(
            shower_id="bad-window",
            name="Bad window",
            radiant=_radiant(),
            activity_start_utc=moment,
            activity_end_utc=moment - timedelta(hours=1),
            source_ids=["iau_mdc_fixture"],
        )


def test_landscape_window_is_geometry_only_and_exposes_blockers():
    target = FixedSkyTarget(
        target_id="galactic-field-fixture",
        name="Galactic field fixture",
        kind=FixedSkyTargetKind.MILKY_WAY_FIELD,
        right_ascension_hours_j2000=17.75,
        declination_deg_j2000=-29.0,
        source_ids=["catalog_fixture"],
        scientific_status=ScientificStatus.HECHO_VERIFICADO,
    )
    start = datetime(2026, 7, 15, 19, 0, tzinfo=UTC)
    plan = plan_landscape_window(
        LandscapeWindowRequest(
            target=target,
            observer=OBSERVER,
            start_utc=start,
            end_utc=start + timedelta(hours=8),
            step_minutes=30,
            minimum_target_altitude_deg=10.0,
            maximum_sun_altitude_deg=-12.0,
        )
    )

    assert plan.samples
    assert plan.scientific_status == ScientificStatus.INFERENCIA
    assert all(0.0 <= sample.geometry_score <= 100.0 for sample in plan.samples)
    assert any("SUN_TOO_HIGH" in sample.blockers for sample in plan.samples)
    assert "Weather" in plan.interpretation
    assert "real horizon" in plan.interpretation


def test_planning_windows_are_bounded_to_prevent_accidental_huge_sampling():
    start = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
    with pytest.raises(ValidationError, match="cannot exceed 72 hours"):
        MeteorWindowRequest(
            shower=_shower(),
            observer=OBSERVER,
            start_utc=start,
            end_utc=start + timedelta(hours=73),
        )
