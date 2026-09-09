import math

from app.models.astrophotography import OpticalTrain, SensorSpec, TargetAngularSize
from app.services.centinela.astrophotography_planner import (
    field_of_view_deg,
    image_scale_arcsec_per_px,
    plan_framing,
    plan_mosaic,
    rotated_target_extents_deg,
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
    assert result.mosaic is not None and result.mosaic.total_panels >= 2
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


def test_target_rotation_changes_sensor_axis_extents():
    target = TargetAngularSize(
        name="rotated",
        major_axis_arcmin=120.0,
        minor_axis_arcmin=30.0,
        position_angle_deg=90.0,
    )
    width, height, relative = rotated_target_extents_deg(
        target, sensor_rotation_deg=0.0
    )
    assert relative == 90.0
    assert math.isclose(width, 0.5, rel_tol=1e-12)
    assert math.isclose(height, 2.0, rel_tol=1e-12)


def test_matching_sensor_rotation_restores_major_axis_to_width():
    target = TargetAngularSize(
        name="rotated",
        major_axis_arcmin=120.0,
        minor_axis_arcmin=30.0,
        position_angle_deg=90.0,
    )
    width, height, relative = rotated_target_extents_deg(
        target, sensor_rotation_deg=90.0
    )
    assert relative == 0.0
    assert math.isclose(width, 2.0, rel_tol=1e-12)
    assert math.isclose(height, 0.5, rel_tol=1e-12)


def test_mosaic_panel_count_accounts_for_overlap_and_margin():
    plan = plan_mosaic(
        target_width_deg=3.0,
        target_height_deg=1.0,
        horizontal_fov_deg=1.2,
        vertical_fov_deg=0.8,
        overlap_fraction=0.15,
        framing_margin_fraction=0.05,
    )
    assert plan.columns == 4
    assert plan.rows == 2
    assert plan.total_panels == 8
    assert plan.effective_coverage_width_deg >= 3.0 * 1.10
    assert plan.effective_coverage_height_deg >= 1.0 * 1.10


def test_single_panel_mosaic_is_reported_when_target_fits_with_margin():
    plan = plan_mosaic(
        target_width_deg=0.5,
        target_height_deg=0.4,
        horizontal_fov_deg=1.0,
        vertical_fov_deg=0.8,
    )
    assert plan.columns == 1
    assert plan.rows == 1
    assert plan.total_panels == 1


def test_optical_train_rejects_payload_above_declared_mount_capacity():
    import pytest

    with pytest.raises(ValueError, match="exceeds declared mount capacity"):
        OpticalTrain(
            aperture_mm=100.0,
            focal_length_mm=700.0,
            mount_payload_capacity_kg=5.0,
            imaging_payload_kg=6.0,
        )
