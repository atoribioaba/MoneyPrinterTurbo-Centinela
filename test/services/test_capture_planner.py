from app.models.astrophotography import (
    CaptureMode,
    CapturePlanningRequest,
    MountTrackingMode,
    OpticalTrain,
    SensorSpec,
    TargetAngularSize,
)
from app.services.centinela.capture_planner import plan_capture


def _sensor():
    return SensorSpec(
        sensor_width_mm=23.5,
        sensor_height_mm=15.6,
        pixel_size_um=3.76,
        width_px=6248,
        height_px=4176,
    )


def test_deep_sky_is_blocked_without_sidereal_tracking():
    result = plan_capture(
        CapturePlanningRequest(
            capture_mode=CaptureMode.DEEP_SKY,
            optical_train=OpticalTrain(
                aperture_mm=80,
                focal_length_mm=480,
                tracking_mode=MountTrackingMode.NONE,
            ),
            sensor=_sensor(),
        )
    )
    assert result.status == "BLOCKED"
    assert "SIDEREAL_TRACKING_REQUIRED_FOR_DEEP_SKY_BASELINE" in result.blockers


def test_solar_capture_fails_closed_without_front_filter_confirmation():
    result = plan_capture(
        CapturePlanningRequest(
            capture_mode=CaptureMode.SOLAR,
            optical_train=OpticalTrain(
                aperture_mm=60,
                focal_length_mm=360,
                tracking_mode=MountTrackingMode.SOLAR,
            ),
            sensor=_sensor(),
            solar_front_aperture_filter_confirmed=False,
        )
    )
    assert result.status == "BLOCKED"
    assert "SOLAR_FRONT_APERTURE_FILTER_NOT_CONFIRMED" in result.blockers


def test_widefield_untracked_avoids_universal_exposure_rule():
    result = plan_capture(
        CapturePlanningRequest(
            capture_mode=CaptureMode.WIDEFIELD,
            optical_train=OpticalTrain(
                aperture_mm=25,
                focal_length_mm=24,
                tracking_mode=MountTrackingMode.NONE,
            ),
            sensor=_sensor(),
        )
    )
    assert result.status == "READY_WITH_WARNINGS"
    assert any("real star-trailing tests" in item for item in result.recommendations)


def test_target_below_horizon_blocks_capture():
    result = plan_capture(
        CapturePlanningRequest(
            capture_mode=CaptureMode.LUNAR,
            optical_train=OpticalTrain(
                aperture_mm=100,
                focal_length_mm=1000,
                tracking_mode=MountTrackingMode.LUNAR,
            ),
            sensor=_sensor(),
            target_altitude_deg=-2.0,
        )
    )
    assert result.status == "BLOCKED"
    assert "TARGET_BELOW_OR_AT_HORIZON" in result.blockers


def test_large_target_returns_mosaic_recommendation():
    result = plan_capture(
        CapturePlanningRequest(
            capture_mode=CaptureMode.DEEP_SKY,
            optical_train=OpticalTrain(
                aperture_mm=100,
                focal_length_mm=700,
                tracking_mode=MountTrackingMode.SIDEREAL,
                mount_payload_capacity_kg=12,
                imaging_payload_kg=7,
            ),
            sensor=_sensor(),
            target=TargetAngularSize(
                name="large",
                major_axis_arcmin=240,
                minor_axis_arcmin=120,
            ),
            guiding_enabled=True,
            requested_total_integration_minutes=180,
        )
    )
    assert result.framing is not None
    assert result.framing.target_fits is False
    assert result.framing.mosaic is not None
    assert any("mosaic baseline" in item for item in result.recommendations)
