import pytest
from pydantic import ValidationError

from app.models.astrophotography import (
    CalibrationFramePlan,
    CalibrationFrameType,
    CaptureMode,
    CapturePlanningRequest,
    FilterCategory,
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


def test_explicit_non_front_solar_filter_class_is_rejected_even_if_boolean_is_true():
    result = plan_capture(
        CapturePlanningRequest(
            capture_mode=CaptureMode.SOLAR,
            optical_train=OpticalTrain(
                aperture_mm=60,
                focal_length_mm=360,
                tracking_mode=MountTrackingMode.SOLAR,
            ),
            sensor=_sensor(),
            solar_front_aperture_filter_confirmed=True,
            filter_category=FilterCategory.BROADBAND,
        )
    )
    assert result.status == "BLOCKED"
    assert "SOLAR_FILTER_CLASS_NOT_FRONT_APERTURE" in result.blockers


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


def test_deep_sky_session_surfaces_guiding_dithering_filter_and_flat_gaps():
    result = plan_capture(
        CapturePlanningRequest(
            capture_mode=CaptureMode.DEEP_SKY,
            optical_train=OpticalTrain(
                aperture_mm=80,
                focal_length_mm=800,
                tracking_mode=MountTrackingMode.SIDEREAL,
                mount_payload_capacity_kg=10,
                imaging_payload_kg=5,
            ),
            sensor=_sensor(),
            guiding_enabled=True,
            guiding_rms_arcsec=2.0,
            dithering_enabled=None,
            filter_category=FilterCategory.UNKNOWN,
            requested_total_integration_minutes=120,
        )
    )

    assert result.status == "READY_WITH_WARNINGS"
    assert "DITHERING_STATE_UNKNOWN" in result.warnings
    assert "FILTER_STATE_UNKNOWN" in result.warnings
    assert "FLAT_CALIBRATION_NOT_PLANNED" in result.warnings
    assert "GUIDING_RMS_LARGER_THAN_IMAGE_SCALE" in result.warnings
    assert any("Record guiding/dithering" in item for item in result.session_checklist)
    assert not any("optimal exposure" in item.lower() for item in result.recommendations)


def test_declared_dark_mismatch_is_flagged_but_bias_dark_flat_are_not_universal():
    result = plan_capture(
        CapturePlanningRequest(
            capture_mode=CaptureMode.DEEP_SKY,
            optical_train=OpticalTrain(
                aperture_mm=80,
                focal_length_mm=480,
                tracking_mode=MountTrackingMode.SIDEREAL,
                mount_payload_capacity_kg=10,
                imaging_payload_kg=5,
            ),
            sensor=_sensor(),
            guiding_enabled=False,
            dithering_enabled=True,
            filter_category=FilterCategory.BROADBAND,
            requested_total_integration_minutes=60,
            calibration_frames=[
                CalibrationFramePlan(
                    frame_type=CalibrationFrameType.FLAT,
                    planned_count=30,
                ),
                CalibrationFramePlan(
                    frame_type=CalibrationFrameType.DARK,
                    planned_count=20,
                    same_exposure_as_lights=False,
                    same_temperature_as_lights=False,
                ),
            ],
        )
    )

    assert "DARK_EXPOSURE_MISMATCH_DECLARED" in result.warnings
    assert "DARK_TEMPERATURE_MISMATCH_DECLARED" in result.warnings
    assert "FLAT_CALIBRATION_NOT_PLANNED" not in result.warnings
    assert all("BIAS" not in item for item in result.blockers + result.warnings)
    assert all("DARK_FLAT" not in item for item in result.blockers + result.warnings)


def test_guiding_rms_cannot_be_claimed_when_guiding_is_disabled():
    with pytest.raises(ValidationError, match="guiding_rms_arcsec"):
        CapturePlanningRequest(
            capture_mode=CaptureMode.DEEP_SKY,
            optical_train=OpticalTrain(
                aperture_mm=80,
                focal_length_mm=480,
                tracking_mode=MountTrackingMode.SIDEREAL,
            ),
            guiding_enabled=False,
            guiding_rms_arcsec=0.8,
        )


def test_duplicate_calibration_frame_types_are_rejected():
    with pytest.raises(ValidationError, match="calibration frame types must be unique"):
        CapturePlanningRequest(
            capture_mode=CaptureMode.DEEP_SKY,
            optical_train=OpticalTrain(
                aperture_mm=80,
                focal_length_mm=480,
                tracking_mode=MountTrackingMode.SIDEREAL,
            ),
            calibration_frames=[
                CalibrationFramePlan(frame_type=CalibrationFrameType.FLAT, planned_count=10),
                CalibrationFramePlan(frame_type=CalibrationFrameType.FLAT, planned_count=20),
            ],
        )
