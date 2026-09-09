from datetime import UTC, datetime, timedelta

from app.models.astrophotography import OpticalTrain, SensorSpec, TargetAngularSize
from app.models.observation import (
    AstronomyConditionsSnapshot,
    EvidenceKind,
    ObservationObjectClass,
    ObservabilityRequest,
    SkyQualityContext,
    WeatherSnapshot,
)
from app.services.centinela.astrophotography_planner import plan_framing
from app.services.centinela.observation_dashboard import build_observation_dashboard
from app.services.centinela.observation_intelligence import evaluate_observability


def test_dashboard_makes_missing_data_textually_explicit_not_color_only():
    request = ObservabilityRequest(
        object_class=ObservationObjectClass.DEEP_SKY,
        target_altitude_deg=60.0,
        sun_altitude_deg=-20.0,
        moon_altitude_deg=-5.0,
        moon_target_separation_deg=120.0,
        moon_illumination_fraction=0.5,
    )
    result = evaluate_observability(request)
    dashboard = build_observation_dashboard(
        title="Deep sky",
        request=request,
        result=result,
        now=datetime(2026, 9, 8, 20, 0, tzinfo=UTC),
    )
    assert dashboard.attention_required is True
    assert "INSUFFICIENT_DATA" in dashboard.attention_reasons
    missing_cards = [item for item in dashboard.metrics if not item.available]
    assert missing_cards
    assert all(item.state_text == "MISSING" for item in missing_cards)
    assert all(item.value_text == "NO DATA" for item in missing_cards)


def test_dashboard_preserves_source_times_and_stale_warning():
    now = datetime(2026, 9, 8, 20, 0, tzinfo=UTC)
    weather = WeatherSnapshot(
        source_id="weather-source",
        valid_at=now,
        retrieved_at=now - timedelta(hours=5),
        cloud_cover_percent=10,
        precipitation_probability_percent=0,
        wind_speed_kph=5,
        temperature_c=10,
        dew_point_c=2,
    )
    astronomy = AstronomyConditionsSnapshot(
        source_id="astro-source",
        valid_at=now,
        retrieved_at=now - timedelta(minutes=30),
        evidence_kind=EvidenceKind.FORECAST,
        seeing_arcsec=1.4,
        transparency_percent=90,
    )
    sky = SkyQualityContext(
        source_id="sqm-source",
        evidence_kind=EvidenceKind.MEASURED,
        sqm_mag_arcsec2=21.3,
    )
    request = ObservabilityRequest(
        object_class=ObservationObjectClass.DEEP_SKY,
        target_altitude_deg=65,
        sun_altitude_deg=-22,
        moon_altitude_deg=-2,
        moon_target_separation_deg=120,
        moon_illumination_fraction=0.4,
        weather=weather,
        astronomy_conditions=astronomy,
        sky_quality=sky,
    )
    dashboard = build_observation_dashboard(
        title="M31",
        request=request,
        result=evaluate_observability(request),
        now=now,
        weather_max_age_hours=3,
    )
    assert "WEATHER_DATA_STALE" in dashboard.attention_reasons
    evidence = {item.source_id: item for item in dashboard.evidence}
    assert evidence["weather-source"].stale is True
    assert evidence["weather-source"].retrieved_at == weather.retrieved_at
    assert evidence["astro-source"].evidence_kind == "forecast"
    assert evidence["sqm-source"].evidence_kind == "measured"


def test_dashboard_includes_astrophotography_framing_without_recalculating_science():
    framing = plan_framing(
        OpticalTrain(aperture_mm=100, focal_length_mm=700),
        SensorSpec(sensor_width_mm=23.5, sensor_height_mm=15.6, pixel_size_um=3.76),
        target=TargetAngularSize(
            name="large",
            major_axis_arcmin=240,
            minor_axis_arcmin=120,
        ),
        seeing_arcsec=2.0,
    )
    request = ObservabilityRequest(
        object_class=ObservationObjectClass.DEEP_SKY,
        target_altitude_deg=60,
        sun_altitude_deg=-20,
        moon_altitude_deg=-5,
        moon_target_separation_deg=120,
        moon_illumination_fraction=0.2,
    )
    dashboard = build_observation_dashboard(
        title="Large target",
        request=request,
        result=evaluate_observability(request),
        now=datetime(2026, 9, 8, 20, 0, tzinfo=UTC),
        framing=framing,
    )
    assert dashboard.framing_summary is not None
    assert dashboard.mosaic_summary is not None
    assert "panels" in dashboard.mosaic_summary
    assert dashboard.sampling_summary is not None
