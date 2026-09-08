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


class OpticalTrain(StrictAstrophotographyModel):
    name: str | None = None
    aperture_mm: float = Field(gt=0.0)
    focal_length_mm: float = Field(gt=0.0)
    focal_multiplier: float = Field(default=1.0, gt=0.0)
    tracking_mode: MountTrackingMode = MountTrackingMode.UNKNOWN


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
    sampling_label: str | None = None
    sampling_pixels_per_seeing_fwhm: float | None = Field(default=None, gt=0.0)
    scientific_status: ScientificStatus = ScientificStatus.APROXIMACION_DIVULGATIVA
    notes: list[str] = Field(default_factory=list)
