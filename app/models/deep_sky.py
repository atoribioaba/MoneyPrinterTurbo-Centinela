from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.astronomy import ScientificStatus


class DeepSkyObject(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    catalog_name: str
    object_type: str
    right_ascension_j2000_hours: float = Field(ge=0.0, lt=24.0)
    declination_j2000_deg: float = Field(ge=-90.0, le=90.0)
    constellation: str

    major_axis_arcmin: float | None = Field(default=None, gt=0.0)
    minor_axis_arcmin: float | None = Field(default=None, gt=0.0)
    position_angle_deg: float | None = Field(default=None, ge=0.0, le=360.0)

    b_magnitude: float | None = None
    v_magnitude: float | None = None
    surface_brightness_mag_arcsec2: float | None = None

    messier_number: int | None = Field(default=None, ge=1, le=110)
    common_names: list[str] = Field(default_factory=list)
    identifiers: list[str] = Field(default_factory=list)
    source_codes: list[str] = Field(default_factory=list)

    source_id: str = "OpenNGC"
    source_license: str = "CC-BY-SA-4.0"
    scientific_status: ScientificStatus = ScientificStatus.HECHO_VERIFICADO
