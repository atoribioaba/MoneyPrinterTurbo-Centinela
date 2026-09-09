from __future__ import annotations

from app.models.astrophotography import (
    CalibrationFrameType,
    CaptureMode,
    CapturePlanningRequest,
    CapturePlanningResult,
    FilterCategory,
    MountTrackingMode,
)
from app.services.centinela.astrophotography_planner import plan_framing


def plan_capture(request: CapturePlanningRequest) -> CapturePlanningResult:
    """Build conservative capture guidance without inventing exposure settings.

    Exposure, gain/ISO and integration depend on real sky, sensor, tracking,
    filters and goals. The planner validates declared prerequisites and session
    evidence; all numeric capture settings remain subject to field validation.
    """
    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []
    checklist: list[str] = []

    framing = None
    if request.sensor is not None:
        framing = plan_framing(
            request.optical_train,
            request.sensor,
            target=request.target,
            seeing_arcsec=request.seeing_arcsec,
        )

    calibration = {item.frame_type: item for item in request.calibration_frames}

    if request.target_altitude_deg is not None and request.target_altitude_deg <= 0:
        blockers.append("TARGET_BELOW_OR_AT_HORIZON")

    if request.capture_mode == CaptureMode.SOLAR:
        if request.solar_front_aperture_filter_confirmed is not True:
            blockers.append("SOLAR_FRONT_APERTURE_FILTER_NOT_CONFIRMED")
        if request.filter_category not in {
            FilterCategory.UNKNOWN,
            FilterCategory.SOLAR_FRONT_APERTURE,
        }:
            blockers.append("SOLAR_FILTER_CLASS_NOT_FRONT_APERTURE")
        elif request.filter_category == FilterCategory.UNKNOWN:
            warnings.append("SOLAR_FILTER_SPEC_NOT_DECLARED")
        recommendations.append(
            "Solar capture requires a purpose-built front-aperture solar filter and manufacturer-compliant use; software never authorizes unfiltered magnified viewing."
        )
        checklist.append("Physically inspect front-aperture solar filter before pointing")

    tracking = request.optical_train.tracking_mode
    if request.capture_mode == CaptureMode.DEEP_SKY:
        if tracking != MountTrackingMode.SIDEREAL:
            blockers.append("SIDEREAL_TRACKING_REQUIRED_FOR_DEEP_SKY_BASELINE")

        if request.guiding_enabled is None:
            warnings.append("GUIDING_STATE_UNKNOWN")
        elif request.guiding_enabled:
            if request.guiding_rms_arcsec is None:
                warnings.append("GUIDING_RMS_UNKNOWN")
            elif (
                framing is not None
                and framing.image_scale_arcsec_per_px is not None
                and request.guiding_rms_arcsec > framing.image_scale_arcsec_per_px
            ):
                warnings.append("GUIDING_RMS_LARGER_THAN_IMAGE_SCALE")
                recommendations.append(
                    "Guiding RMS exceeds the calculated image scale; validate star shape on real subs before committing to the session."
                )

        if request.dithering_enabled is None:
            warnings.append("DITHERING_STATE_UNKNOWN")
        elif request.dithering_enabled is False:
            recommendations.append(
                "Consider dithering between groups of subexposures when the acquisition software and guiding workflow support it; validate settling time empirically."
            )

        if request.requested_subexposure_seconds is not None:
            recommendations.append(
                "Validate requested subexposure empirically against star eccentricity, clipping, sky background and guiding RMS before adopting it."
            )
        if request.requested_total_integration_minutes is None:
            warnings.append("TOTAL_INTEGRATION_NOT_DECLARED")

        flat_plan = calibration.get(CalibrationFrameType.FLAT)
        if flat_plan is None or flat_plan.planned_count == 0:
            warnings.append("FLAT_CALIBRATION_NOT_PLANNED")
            recommendations.append(
                "Plan flats for the final optical train when vignetting/dust calibration matters; do not reuse mismatched flats silently."
            )

        dark_plan = calibration.get(CalibrationFrameType.DARK)
        if dark_plan is not None and dark_plan.planned_count > 0:
            if dark_plan.same_exposure_as_lights is False:
                warnings.append("DARK_EXPOSURE_MISMATCH_DECLARED")
            if dark_plan.same_temperature_as_lights is False:
                warnings.append("DARK_TEMPERATURE_MISMATCH_DECLARED")
        else:
            recommendations.append(
                "Whether darks are beneficial is camera/workflow-specific; decide from real sensor behaviour rather than a universal rule."
            )

        if request.filter_category == FilterCategory.UNKNOWN:
            warnings.append("FILTER_STATE_UNKNOWN")
        checklist.extend(
            [
                "Verify focus after final filter/optical-train configuration",
                "Inspect first real subexposures for clipping, trailing and gradients",
                "Record guiding/dithering state and filter identity in session provenance",
            ]
        )

    if request.capture_mode == CaptureMode.WIDEFIELD:
        if tracking == MountTrackingMode.NONE:
            recommendations.append(
                "For untracked wide-field capture, determine the longest acceptable exposure from real star-trailing tests for this camera, focal length, declination and output scale; do not rely on one universal rule."
            )
        elif tracking == MountTrackingMode.UNKNOWN:
            warnings.append("TRACKING_STATE_UNKNOWN")
        flat_plan = calibration.get(CalibrationFrameType.FLAT)
        if flat_plan is None or flat_plan.planned_count == 0:
            recommendations.append(
                "Evaluate whether flats are needed for the lens/aperture and final processing workflow."
            )

    if request.capture_mode in {CaptureMode.PLANETARY, CaptureMode.LUNAR}:
        recommendations.append(
            "Prefer high-frame-count lucky imaging and validate focus, histogram and seeing on the live target; final frame selection and stacking remain empirical."
        )
        if request.seeing_arcsec is None:
            warnings.append("SEEING_NOT_MEASURED_OR_PROVIDED")
        checklist.append("Validate histogram and focus on the live target before the main capture")

    if request.capture_mode == CaptureMode.SMARTPHONE:
        recommendations.append(
            "Treat computational multi-frame modes as camera-specific processing; preserve an original file when possible and record device/app settings in provenance."
        )

    if request.preserve_raw_or_lossless_source is False:
        warnings.append("RAW_OR_LOSSLESS_SOURCE_NOT_PRESERVED")
    elif request.preserve_raw_or_lossless_source is None:
        recommendations.append(
            "Record whether an original RAW/lossless acquisition is preserved for reproducibility and future reprocessing."
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
        session_checklist=checklist,
        framing=framing,
    )
