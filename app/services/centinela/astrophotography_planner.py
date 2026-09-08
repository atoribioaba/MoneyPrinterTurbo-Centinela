from __future__ import annotations

import math

from app.models.astrophotography import (
    FramingResult,
    MosaicPlan,
    OpticalTrain,
    SensorSpec,
    TargetAngularSize,
)


_ARCSEC_PER_RADIAN = 206264.80624709636


def effective_focal_length_mm(optical_train: OpticalTrain) -> float:
    return optical_train.focal_length_mm * optical_train.focal_multiplier


def focal_ratio(optical_train: OpticalTrain) -> float:
    return effective_focal_length_mm(optical_train) / optical_train.aperture_mm


def field_of_view_deg(sensor_size_mm: float, focal_length_mm: float) -> float:
    """Exact rectilinear angular field for one sensor dimension."""
    return math.degrees(2.0 * math.atan(sensor_size_mm / (2.0 * focal_length_mm)))


def image_scale_arcsec_per_px(
    pixel_size_um: float,
    focal_length_mm: float,
) -> float:
    """Angular pixel scale from physical pixel pitch and effective focal length."""
    return _ARCSEC_PER_RADIAN * (pixel_size_um / 1000.0) / focal_length_mm


def sampling_assessment(
    image_scale_arcsec_px: float | None,
    seeing_arcsec: float | None,
) -> tuple[str | None, float | None, str | None]:
    """Return a conservative seeing-to-pixel sampling interpretation.

    This is intentionally an approximation: seeing varies with time, wavelength,
    altitude and site. The result is guidance, never a guarantee of recoverable
    spatial resolution.
    """
    if image_scale_arcsec_px is None or seeing_arcsec is None:
        return None, None, None
    if seeing_arcsec <= 0:
        raise ValueError("seeing_arcsec must be positive")

    pixels_per_fwhm = seeing_arcsec / image_scale_arcsec_px
    if pixels_per_fwhm < 1.5:
        label = "UNDERSAMPLED_FOR_REPORTED_SEEING"
    elif pixels_per_fwhm <= 3.5:
        label = "BALANCED_FOR_REPORTED_SEEING"
    else:
        label = "OVERSAMPLED_FOR_REPORTED_SEEING"

    note = (
        "Sampling label is an approximation based on the supplied seeing FWHM; "
        "it does not replace a real star-profile measurement."
    )
    return label, pixels_per_fwhm, note


def _normalize_half_turn(angle_deg: float) -> float:
    return float(angle_deg) % 180.0


def rotated_target_extents_deg(
    target: TargetAngularSize,
    *,
    sensor_rotation_deg: float = 0.0,
) -> tuple[float, float, float | None]:
    """Return target bounding-box extents in sensor coordinates.

    The target is approximated as an ellipse whose major/minor axes come from
    catalog angular dimensions. If a catalog position angle is unavailable,
    the major axis is conservatively aligned with the sensor width and no
    rotation benefit is claimed.
    """
    major_deg = target.major_axis_arcmin / 60.0
    minor_deg = target.minor_axis_arcmin / 60.0
    if target.position_angle_deg is None:
        return major_deg, minor_deg, None

    relative = _normalize_half_turn(target.position_angle_deg - sensor_rotation_deg)
    theta = math.radians(relative)
    width = math.sqrt(
        (major_deg * math.cos(theta)) ** 2
        + (minor_deg * math.sin(theta)) ** 2
    )
    height = math.sqrt(
        (major_deg * math.sin(theta)) ** 2
        + (minor_deg * math.cos(theta)) ** 2
    )
    return width, height, relative


def _panels_for_extent(
    target_extent_deg: float,
    fov_deg: float,
    overlap_fraction: float,
) -> int:
    if not 0.0 <= overlap_fraction < 1.0:
        raise ValueError("mosaic overlap must be in [0, 1)")
    if target_extent_deg <= fov_deg:
        return 1
    step = fov_deg * (1.0 - overlap_fraction)
    if step <= 0.0:
        raise ValueError("mosaic step must be positive")
    return 1 + math.ceil((target_extent_deg - fov_deg) / step)


def plan_mosaic(
    *,
    target_width_deg: float,
    target_height_deg: float,
    horizontal_fov_deg: float,
    vertical_fov_deg: float,
    overlap_fraction: float = 0.15,
    framing_margin_fraction: float = 0.05,
) -> MosaicPlan:
    """Return a deterministic rectangular mosaic plan.

    A small framing margin can be requested to avoid designing a mosaic whose
    useful coverage exactly touches the catalog target boundary. The result is
    geometric only; mount repeatability, distortion and low-surface-brightness
    extensions still require field validation.
    """
    if not 0.0 <= framing_margin_fraction < 1.0:
        raise ValueError("framing margin must be in [0, 1)")
    required_width = target_width_deg * (1.0 + 2.0 * framing_margin_fraction)
    required_height = target_height_deg * (1.0 + 2.0 * framing_margin_fraction)

    columns = _panels_for_extent(required_width, horizontal_fov_deg, overlap_fraction)
    rows = _panels_for_extent(required_height, vertical_fov_deg, overlap_fraction)
    width_step = horizontal_fov_deg * (1.0 - overlap_fraction)
    height_step = vertical_fov_deg * (1.0 - overlap_fraction)
    coverage_width = horizontal_fov_deg + (columns - 1) * width_step
    coverage_height = vertical_fov_deg + (rows - 1) * height_step

    return MosaicPlan(
        columns=columns,
        rows=rows,
        total_panels=columns * rows,
        overlap_fraction=overlap_fraction,
        effective_coverage_width_deg=round(coverage_width, 6),
        effective_coverage_height_deg=round(coverage_height, 6),
    )


def plan_framing(
    optical_train: OpticalTrain,
    sensor: SensorSpec,
    target: TargetAngularSize | None = None,
    seeing_arcsec: float | None = None,
    *,
    sensor_rotation_deg: float = 0.0,
    mosaic_overlap_fraction: float = 0.15,
    framing_margin_fraction: float = 0.05,
) -> FramingResult:
    sensor_rotation_deg = _normalize_half_turn(sensor_rotation_deg)
    focal = effective_focal_length_mm(optical_train)
    horizontal = field_of_view_deg(sensor.sensor_width_mm, focal)
    vertical = field_of_view_deg(sensor.sensor_height_mm, focal)
    diagonal_mm = math.hypot(sensor.sensor_width_mm, sensor.sensor_height_mm)
    diagonal = field_of_view_deg(diagonal_mm, focal)

    image_scale = None
    if sensor.pixel_size_um is not None:
        image_scale = image_scale_arcsec_per_px(sensor.pixel_size_um, focal)

    target_fits = None
    width_fraction = None
    height_fraction = None
    relative_target_angle = None
    mosaic = None
    notes: list[str] = []

    if target is not None:
        target_width_deg, target_height_deg, relative_target_angle = (
            rotated_target_extents_deg(
                target,
                sensor_rotation_deg=sensor_rotation_deg,
            )
        )
        margin_multiplier = 1.0 + 2.0 * framing_margin_fraction
        width_fraction = target_width_deg * margin_multiplier / horizontal
        height_fraction = target_height_deg * margin_multiplier / vertical
        target_fits = width_fraction <= 1.0 and height_fraction <= 1.0
        mosaic = plan_mosaic(
            target_width_deg=target_width_deg,
            target_height_deg=target_height_deg,
            horizontal_fov_deg=horizontal,
            vertical_fov_deg=vertical,
            overlap_fraction=mosaic_overlap_fraction,
            framing_margin_fraction=framing_margin_fraction,
        )

        if target.position_angle_deg is None:
            notes.append(
                "Target position angle is unavailable; no rotation benefit is claimed."
            )
        else:
            notes.append(
                "Target framing uses catalog position angle relative to the declared sensor rotation."
            )
        if target_fits:
            notes.append("Target fits inside the sensor field with the requested margin.")
        else:
            notes.append(
                "Target does not fit in one panel; the returned mosaic is the minimum rectangular geometric plan."
            )
        notes.append(
            "Framing uses catalog angular dimensions only and does not model faint extensions, distortion or dithering losses."
        )

    sampling_label, pixels_per_fwhm, sampling_note = sampling_assessment(
        image_scale, seeing_arcsec
    )
    if sampling_note:
        notes.append(sampling_note)

    return FramingResult(
        effective_focal_length_mm=round(focal, 6),
        focal_ratio=round(focal_ratio(optical_train), 6),
        horizontal_fov_deg=round(horizontal, 6),
        vertical_fov_deg=round(vertical, 6),
        diagonal_fov_deg=round(diagonal, 6),
        image_scale_arcsec_per_px=(round(image_scale, 6) if image_scale else None),
        target_fits=target_fits,
        target_width_fraction=(round(width_fraction, 6) if width_fraction else None),
        target_height_fraction=(round(height_fraction, 6) if height_fraction else None),
        sensor_rotation_deg=round(sensor_rotation_deg, 6),
        relative_target_angle_deg=(
            round(relative_target_angle, 6) if relative_target_angle is not None else None
        ),
        mosaic=mosaic,
        sampling_label=sampling_label,
        sampling_pixels_per_seeing_fwhm=(
            round(pixels_per_fwhm, 6) if pixels_per_fwhm else None
        ),
        notes=notes,
    )
