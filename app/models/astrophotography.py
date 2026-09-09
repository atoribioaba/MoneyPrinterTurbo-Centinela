from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astronomy import ScientificStatus


class StrictAstrophotographyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class MountTrackingMode(str, Enum):
    NONE = "none"
    SIDEREAL = "sidereal"
    SOLAR = "solar"
    LUNAR = "lunar"
    UNKNOWN = "unknown"


class CaptureMode(str, Enum):
    VISUAL = "visual"
    SMARTPHONE = "smartphone"
    WIDEFIELD = "widefield"
    DEEP_SKY = "deep_sky"
    PLANETARY = "planetary"
    LUNAR = "lunar"
    SOLAR = "solar"


class FilterCategory(str, Enum):
    UNKNOWN = "unknown"
    NONE = "none"
    BROADBAND = "broadband"
    NARROWBAND = "narrowband"
    DUAL_BAND = "dual_band"
    SOLAR_FRONT_APERTURE = "solar_front_aperture"
    OTHER = "other"


class CalibrationFrameType(str, Enum):
    DARK = "dark"
    FLAT = "flat"
    BIAS = "bias"
    DARK_FLAT = "dark_flat"


class CalibrationFramePlan(StrictAstrophotographyModel):
    frame_type: CalibrationFrameType
    planned_count: int = Field(ge=0)
    same_exposure_as_lights: bool | None = None
    same_temperature_as_lights: bool | None = None
    notes: str = ""


class OpticalTrain(StrictAstrophotographyModel):
    name: str | None = None
    aperture_mm: float = Field(gt=0.0)
    focal_length_mm: float = Field(gt=0.0)
    focal_multiplier: float = Field(default=1.0, gt=0.0)
    tracking_mode: MountTrackingMode = MountTrackingMode.UNKNOWN
    mount_payload_capacity_kg: float | None = Field(default=None, gt=0.0)
    imaging_payload_kg: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def validate_payload(self):
        if (
            self.mount_payload_capacity_kg is not None
            and self.imaging_payload_kg is not None
            and self.imaging_payload_kg > self.mount_payload_capacity_kg
        ):
            raise ValueError("imaging payload exceeds declared mount capacity")
        return self


class SensorSpec(StrictAstrophotographyModel):
    name: str | None = None
    sensor_width_mm: float = Field(gt=0.0)
    sensor_height_mm: float = Field(gt=0.0)
    pixel_size_um: float | None = Field(default=None, gt=0.0)
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_pixel_dimensions(self):
        if (self.width_px is None) != (self.height_px is None):
            raise ValueError("width_px and height_px must be provided together")
        return self


class TargetAngularSize(StrictAstrophotographyModel):
    name: str
    major_axis_arcmin: float = Field(gt=0.0)
    minor_axis_arcmin: float = Field(gt=0.0)
    position_angle_deg: float | None = Field(default=None, ge=0.0, lt=180.0)


class MosaicPlan(StrictAstrophotographyModel):
    columns: int = Field(ge=1)
    rows: int = Field(ge=1)
    total_panels: int = Field(ge=1)
    overlap_fraction: float = Field(ge=0.0, lt=1.0)
    effective_coverage_width_deg: float = Field(gt=0.0)
    effective_coverage_height_deg: float = Field(gt=0.0)

    @model_validator(mode="after")
    def validate_panel_count(self):
        if self.total_panels != self.columns * self.rows:
            raise ValueError("total_panels must equal columns * rows")
        return self


class FramingResult(StrictAstrophotographyModel):
    effective_focal_length_mm: float = Field(gt=0.0)
    focal_ratio: float = Field(gt=0.0)
    horizontal_fov_deg: float = Field(gt=0.0, le=180.0)
    vertical_fov_deg: float = Field(gt=0.0, le=180.0)
    diagonal_fov_deg: float = Field(gt=0.0, le=180.0)
    image_scale_arcsec_per_px: float | None = Field(default=None, gt=0.0)
    target_fits: bool | None = None
    target_width_fraction: float | None = Field(default=None, gt=0.0)
    target_height_fraction: float | None = Field(default=None, gt=0.0)
    sensor_rotation_deg: float = Field(default=0.0, ge=0.0, lt=180.0)
    relative_target_angle_deg: float | None = Field(default=None, ge=0.0, lt=180.0)
    mosaic: MosaicPlan | None = None
    sampling_label: str | None = None
    sampling_pixels_per_seeing_fwhm: float | None = Field(default=None, gt=0.0)
    scientific_status: ScientificStatus = ScientificStatus.APROXIMACION_DIVULGATIVA
    notes: list[str] = Field(default_factory=list)


class CapturePlanningRequest(StrictAstrophotographyModel):
    capture_mode: CaptureMode
    optical_train: OpticalTrain
    sensor: SensorSpec | None = None
    target: TargetAngularSize | None = None
    seeing_arcsec: float | None = Field(default=None, gt=0.0)
    target_altitude_deg: float | None = Field(default=None, ge=-90.0, le=90.0)
    requested_subexposure_seconds: float | None = Field(default=None, gt=0.0)
    requested_total_integration_minutes: float | None = Field(default=None, gt=0.0)
    guiding_enabled: bool | None = None
    guiding_rms_arcsec: float | None = Field(default=None, gt=0.0)
    dithering_enabled: bool | None = None
    filter_category: FilterCategory = FilterCategory.UNKNOWN
    filter_name: str | None = None
    calibration_frames: list[CalibrationFramePlan] = Field(default_factory=list)
    cooling_setpoint_c: float | None = None
    preserve_raw_or_lossless_source: bool | None = None
    solar_front_aperture_filter_confirmed: bool | None = None

    @model_validator(mode="after")
    def validate_session_inputs(self):
        if self.guiding_enabled is False and self.guiding_rms_arcsec is not None:
            raise ValueError("guiding_rms_arcsec cannot be supplied when guiding is disabled")
        frame_types = [item.frame_type for item in self.calibration_frames]
        if len(frame_types) != len(set(frame_types)):
            raise ValueError("calibration frame types must be unique")
        if self.filter_name is not None and not self.filter_name.strip():
            raise ValueError("filter_name cannot be blank")
        return self


class CapturePlanningResult(StrictAstrophotographyModel):
    status: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    session_checklist: list[str] = Field(default_factory=list)
    framing: FramingResult | None = None
    scientific_status: ScientificStatus = ScientificStatus.APROXIMACION_DIVULGATIVA
