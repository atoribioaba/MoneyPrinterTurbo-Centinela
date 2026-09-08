import math

from app.models.observation import (
    EvidenceKind,
    ObservationObjectClass,
    ObservabilityRequest,
    SkyQualityContext,
    WeatherSnapshot,
)
from app.services.centinela.observation_intelligence import (
    airmass_from_altitude_deg,
    angular_separation_deg,
    evaluate_observability,
)


def test_airmass_is_none_below_horizon_and_near_one_at_zenith():
    assert airmass_from_altitude_deg(0.0) is None
    assert airmass_from_altitude_deg(-5.0) is None
    assert math.isclose(airmass_from_altitude_deg(90.0), 0.9997, rel_tol=2e-3)


def test_angular_separation_handles_wraparound():
    assert math.isclose(angular_separation_deg(23.9, 0.0, 0.1, 0.0), 3.0, rel_tol=1e-6)


def test_missing_weather_does_not_masquerade_as_excellent_conditions():
    result = evaluate_observability(
        ObservabilityRequest(
            object_class=ObservationObjectClass.DEEP_SKY,
            target_altitude_deg=70.0,
            sun_altitude_deg=-20.0,
            moon_altitude_deg=-10.0,
            moon_target_separation_deg=90.0,
            moon_illumination_fraction=0.8,
        )
    )
    assert result.completeness_percent < 50.0
    assert result.grade == "INSUFFICIENT_DATA"
    assert "clouds" in result.missing_inputs
    assert "sky_quality" in result.missing_inputs


def test_complete_good_deep_sky_conditions_score_high():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    weather = WeatherSnapshot(
        source_id="fixture-weather",
        valid_at=now,
        retrieved_at=now,
        evidence_kind=EvidenceKind.FORECAST,
        temperature_c=8.0,
        dew_point_c=1.0,
        cloud_cover_percent=2.0,
        transparency_percent=95.0,
        seeing_arcsec=1.5,
        wind_speed_kph=5.0,
    )
    sky = SkyQualityContext(
        source_id="fixture-sqm",
        evidence_kind=EvidenceKind.MEASURED,
        sqm_mag_arcsec2=21.6,
    )
    result = evaluate_observability(
        ObservabilityRequest(
            object_class=ObservationObjectClass.DEEP_SKY,
            target_altitude_deg=65.0,
            sun_altitude_deg=-22.0,
            moon_altitude_deg=-5.0,
            moon_target_separation_deg=120.0,
            moon_illumination_fraction=0.9,
            weather=weather,
            sky_quality=sky,
        )
    )
    assert result.completeness_percent == 100.0
    assert result.score is not None and result.score >= 85.0
    assert result.grade == "EXCELLENT"
    assert result.scientific_status.value == "INFERENCIA"


def test_planetary_weights_seeing_more_than_dark_sky_quality():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    poor_seeing = WeatherSnapshot(
        source_id="fixture-weather",
        valid_at=now,
        retrieved_at=now,
        cloud_cover_percent=0.0,
        transparency_percent=100.0,
        seeing_arcsec=4.0,
        wind_speed_kph=0.0,
        temperature_c=10.0,
        dew_point_c=0.0,
    )
    sky = SkyQualityContext(
        source_id="fixture-sky",
        evidence_kind=EvidenceKind.MAP_DERIVED,
        bortle_class=1,
    )
    result = evaluate_observability(
        ObservabilityRequest(
            object_class=ObservationObjectClass.PLANETARY,
            target_altitude_deg=70.0,
            sun_altitude_deg=-12.0,
            moon_altitude_deg=-1.0,
            moon_target_separation_deg=90.0,
            moon_illumination_fraction=1.0,
            weather=poor_seeing,
            sky_quality=sky,
        )
    )
    seeing_component = next(c for c in result.components if c.name == "seeing")
    sky_component = next(c for c in result.components if c.name == "sky_quality")
    assert seeing_component.weight > sky_component.weight
    assert seeing_component.score == 0.0
