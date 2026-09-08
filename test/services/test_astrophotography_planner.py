import math

from app.models.astrophotography import OpticalTrain, SensorSpec, TargetAngularSize
from app.services.centinela.astrophotography_planner import (
    field_of_view_deg,
    image_scale_arcsec_per_px,
    plan_framing,
)


def test_field_of_view_uses_exact_rectilinear_formula():
    result = field_of_view_deg(36.0, 50.0)
    expected = math.degrees(2.0 * math.atan(36.0 / 100.0))
    assert math.isclose(result, expected, rel_tol=1e-12)


def test_image_scale_matches_standard_geometry():
    # 3.76 um pixels at 1000 mm are about 0.776 arcsec/px.
    scale = image_scale_arcsec_per_px(3.76, 1000.0)
    assert math.isclose(scale, 0.7756, rel_tol=2e-3)


def test_plan_framing_reports_target_fit_and_sampling():
    optical = OpticalTrain(aperture_mm=100.0, focal_length_mm=500.0)
    sensor = SensorSpec(
        sensor_width_mm=23.5,
        sensor_height_mm=15.6,
        pixel_size_um=3.76,
        width_px=6248,
        height_px=4176,
    )
    target = TargetAngularSize(
        name="fixture-target",
        major_axis_arcmin=180.0,
        minor_axis_arcmin=60.0,
    )
    result = plan_framing(optical, sensor, target=target, seeing_arcsec=2.0)

    assert result.effective_focal_length_mm == 500.0
    assert result.focal_ratio == 5.0
    assert result.target_fits is False
    assert result.image_scale_arcsec_per_px is not None
    assert result.sampling_label is not None
    assert result.scientific_status.value == "APROXIMACION_DIVULGATIVA"


def test_focal_multiplier_changes_fov_and_f_ratio():
    native = OpticalTrain(aperture_mm=80.0, focal_length_mm=400.0)
    barlowed = OpticalTrain(
        aperture_mm=80.0,
        focal_length_mm=400.0,
        focal_multiplier=2.0,
    )
    sensor = SensorSpec(sensor_width_mm=10.0, sensor_height_mm=7.5)

    native_result = plan_framing(native, sensor)
    barlow_result = plan_framing(barlowed, sensor)

    assert barlow_result.effective_focal_length_mm == 800.0
    assert barlow_result.focal_ratio == 10.0
    assert barlow_result.horizontal_fov_deg < native_result.horizontal_fov_deg


def test_sampling_is_not_claimed_without_pixel_size_or_seeing():
    optical = OpticalTrain(aperture_mm=80.0, focal_length_mm=400.0)
    sensor = SensorSpec(sensor_width_mm=10.0, sensor_height_mm=7.5)
    result = plan_framing(optical, sensor)
    assert result.image_scale_arcsec_per_px is None
    assert result.sampling_label is None
