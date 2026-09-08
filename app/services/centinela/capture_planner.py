from __future__ import annotations

from app.models.astrophotography import (
    CaptureMode,
    CapturePlanningRequest,
    CapturePlanningResult,
    MountTrackingMode,
)
from app.services.centinela.astrophotography_planner import plan_framing


def plan_capture(request: CapturePlanningRequest) -> CapturePlanningResult:
    """Build conservative capture guidance without inventing exposure settings.

    Exposure time, gain/ISO and total integration depend on sky brightness,
    target surface brightness, sensor characteristics, tracking/guiding quality,
    filters and the desired scientific/aesthetic result. This planner therefore
    validates prerequisites and returns bounded guidance rather than pretending
    a universal numeric recipe is physically optimal.
    """
    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    framing = None
    if request.sensor is not None:
        framing = plan_framing(
            request.optical_train,
            request.sensor,
            target=request.target,
            seeing_arcsec=request.seeing_arcsec,
        )

    if request.target_altitude_deg is not None and request.target_altitude_deg <= 0:
        blockers.append("TARGET_BELOW_OR_AT_HORIZON")

    if request.capture_mode == CaptureMode.SOLAR:
        if request.solar_front_aperture_filter_confirmed is not True:
            blockers.append("SOLAR_FRONT_APERTURE_FILTER_NOT_CONFIRMED")
        recommendations.append(
            "Solar capture requires a purpose-built front-aperture solar filter and manufacturer-compliant use; software never authorizes unfiltered magnified viewing."
        )

    tracking = request.optical_train.tracking_mode
    if request.capture_mode == CaptureMode.DEEP_SKY:
        if tracking not in {MountTrackingMode.SIDEREAL}:
            blockers.append("SIDEREAL_TRACKING_REQUIRED_FOR_DEEP_SKY_BASELINE")
        if request.guiding_enabled is None:
            warnings.append("GUIDING_STATE_UNKNOWN")
        if request.requested_subexposure_seconds is not None:
            recommendations.append(
                "Validate requested subexposure empirically against star eccentricity, clipping, sky background and guiding RMS before adopting it."
            )
        if request.requested_total_integration_minutes is None:
            warnings.append("TOTAL_INTEGRATION_NOT_DECLARED")

    if request.capture_mode == CaptureMode.WIDEFIELD:
        if tracking == MountTrackingMode.NONE:
            recommendations.append(
                "For untracked wide-field capture, determine the longest acceptable exposure from real star-trailing tests for this camera, focal length, declination and output scale; do not rely on one universal rule."
            )
        elif tracking == MountTrackingMode.UNKNOWN:
            warnings.append("TRACKING_STATE_UNKNOWN")

    if request.capture_mode in {CaptureMode.PLANETARY, CaptureMode.LUNAR}:
        recommendations.append(
            "Prefer high-frame-count lucky imaging and validate focus, histogram and seeing on the live target; final frame selection and stacking remain empirical."
        )
        if request.seeing_arcsec is None:
            warnings.append("SEEING_NOT_MEASURED_OR_PROVIDED")

    if request.capture_mode == CaptureMode.SMARTPHONE:
        recommendations.append(
            "Treat computational multi-frame modes as camera-specific processing; preserve an original file when possible and record device/app settings in provenance."
        )

    if request.optical_train.mount_payload_capacity_kg is None:
        warnings.append("MOUNT_PAYLOAD_CAPACITY_UNKNOWN")
    elif request.optical_train.imaging_payload_kg is None:
        warnings.append("IMAGING_PAYLOAD_UNKNOWN")
    else:
        utilization = (
            request.optical_train.imaging_payload_kg
            / request.optical_train.mount_payload_capacity_kg
        )
        if utilization >= 0.9:
            warnings.append("MOUNT_PAYLOAD_NEAR_DECLARED_CAPACITY")

    if framing is not None and framing.target_fits is False:
        recommendations.append(
            f"Use the geometric mosaic baseline: {framing.mosaic.columns}×{framing.mosaic.rows} panels ({framing.mosaic.total_panels} total)."
        )

    if blockers:
        status = "BLOCKED"
    elif warnings:
        status = "READY_WITH_WARNINGS"
    else:
        status = "READY_FOR_FIELD_VALIDATION"

    return CapturePlanningResult(
        status=status,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        recommendations=recommendations,
        framing=framing,
    )
