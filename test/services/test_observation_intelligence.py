import math

from app.models.observation import (
    AstronomyConditionsSnapshot,
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
    assert math.isclose(
        angular_separation_deg(23.9, 0.0, 0.1, 0.0),
        3.0,
        rel_tol=1e-6,
    )


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
    assert "precipitation" in result.missing_inputs
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
        precipitation_probability_percent=0.0,
        transparency_percent=95.0,
        seeing_arcsec=1.5,
        wind_speed_kph=5.0,
        wind_gust_kph=7.0,
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
        precipitation_probability_percent=0.0,
        transparency_percent=100.0,
        seeing_arcsec=4.0,
        wind_speed_kph=0.0,
        wind_gust_kph=0.0,
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


def test_precipitation_is_explicitly_penalized():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    weather = WeatherSnapshot(
        source_id="rain-fixture",
        valid_at=now,
        retrieved_at=now,
        cloud_cover_percent=0.0,
        precipitation_probability_percent=100.0,
        transparency_percent=100.0,
        seeing_arcsec=1.0,
        wind_speed_kph=0.0,
        wind_gust_kph=0.0,
        temperature_c=10.0,
        dew_point_c=0.0,
    )
    sky = SkyQualityContext(
        source_id="dark-sky-fixture",
        evidence_kind=EvidenceKind.MEASURED,
        sqm_mag_arcsec2=21.7,
    )
    result = evaluate_observability(
        ObservabilityRequest(
            object_class=ObservationObjectClass.DEEP_SKY,
            target_altitude_deg=70.0,
            sun_altitude_deg=-20.0,
            moon_altitude_deg=-5.0,
            moon_target_separation_deg=120.0,
            moon_illumination_fraction=0.0,
            weather=weather,
            sky_quality=sky,
        )
    )
    component = next(c for c in result.components if c.name == "precipitation")
    assert component.score == 0.0


def test_wind_component_uses_worst_reported_gust():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    weather = WeatherSnapshot(
        source_id="gust-fixture",
        valid_at=now,
        retrieved_at=now,
        cloud_cover_percent=0.0,
        precipitation_probability_percent=0.0,
        transparency_percent=100.0,
        seeing_arcsec=1.0,
        wind_speed_kph=5.0,
        wind_gust_kph=45.0,
        temperature_c=10.0,
        dew_point_c=0.0,
    )
    result = evaluate_observability(
        ObservabilityRequest(
            object_class=ObservationObjectClass.LUNAR,
            target_altitude_deg=70.0,
            sun_altitude_deg=-8.0,
            weather=weather,
        )
    )
    component = next(c for c in result.components if c.name == "wind")
    assert component.score < 20.0
    assert "45.0 km/h" in component.rationale


def test_astronomy_conditions_preserve_separate_source_provenance():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    weather = WeatherSnapshot(
        source_id="open-meteo-fixture",
        valid_at=now,
        retrieved_at=now,
        cloud_cover_percent=5.0,
        precipitation_probability_percent=0.0,
        wind_speed_kph=4.0,
        wind_gust_kph=6.0,
        temperature_c=9.0,
        dew_point_c=1.0,
    )
    astronomy = AstronomyConditionsSnapshot(
        source_id="astro-weather-fixture",
        valid_at=now,
        retrieved_at=now,
        evidence_kind=EvidenceKind.FORECAST,
        seeing_arcsec=1.2,
        transparency_percent=92.0,
    )
    sky = SkyQualityContext(
        source_id="sqm-meter-fixture",
        evidence_kind=EvidenceKind.MEASURED,
        sqm_mag_arcsec2=21.4,
    )
    result = evaluate_observability(
        ObservabilityRequest(
            object_class=ObservationObjectClass.DEEP_SKY,
            target_altitude_deg=65.0,
            sun_altitude_deg=-22.0,
            moon_altitude_deg=-2.0,
            moon_target_separation_deg=100.0,
            moon_illumination_fraction=0.5,
            weather=weather,
            astronomy_conditions=astronomy,
            sky_quality=sky,
        )
    )
    seeing = next(c for c in result.components if c.name == "seeing")
    clouds = next(c for c in result.components if c.name == "clouds")
    sky_component = next(c for c in result.components if c.name == "sky_quality")
    assert seeing.source_ids == ["astro-weather-fixture"]
    assert clouds.source_ids == ["open-meteo-fixture"]
    assert sky_component.source_ids == ["sqm-meter-fixture"]
    assert result.input_source_ids == [
        "astro-weather-fixture",
        "open-meteo-fixture",
        "sqm-meter-fixture",
    ]
