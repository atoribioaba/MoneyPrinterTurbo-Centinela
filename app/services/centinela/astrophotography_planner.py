from __future__ import annotations

import math

from app.models.astrophotography import (
    FramingResult,
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


def plan_framing(
    optical_train: OpticalTrain,
    sensor: SensorSpec,
    target: TargetAngularSize | None = None,
    seeing_arcsec: float | None = None,
) -> FramingResult:
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
    notes: list[str] = []

    if target is not None:
        target_major_deg = target.major_axis_arcmin / 60.0
        target_minor_deg = target.minor_axis_arcmin / 60.0
        width_fraction = target_major_deg / horizontal
        height_fraction = target_minor_deg / vertical
        target_fits = width_fraction <= 1.0 and height_fraction <= 1.0
        if target_fits:
            notes.append(
                "Target angular dimensions fit inside the unrotated sensor field."
            )
        else:
            notes.append(
                "Target does not fit inside the unrotated sensor field; rotation or mosaic planning may be required."
            )
        notes.append(
            "Framing uses catalog angular dimensions only and does not model low-surface-brightness extensions."
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
        sampling_label=sampling_label,
        sampling_pixels_per_seeing_fwhm=(
            round(pixels_per_fwhm, 6) if pixels_per_fwhm else None
        ),
        notes=notes,
    )
