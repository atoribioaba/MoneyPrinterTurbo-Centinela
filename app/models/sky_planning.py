from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.astronomy import ScientificStatus


class StrictSkyPlanningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class FixedSkyTargetKind(str, Enum):
    DEEP_SKY = "deep_sky"
    METEOR_RADIANT = "meteor_radiant"
    GALACTIC_CENTER = "galactic_center"
    MILKY_WAY_FIELD = "milky_way_field"
    STAR = "star"
    OTHER = "other"


class FixedSkyTarget(StrictSkyPlanningModel):
    target_id: str
    name: str
    kind: FixedSkyTargetKind
    right_ascension_hours_j2000: float = Field(ge=0.0, lt=24.0)
    declination_deg_j2000: float = Field(ge=-90.0, le=90.0)
    source_ids: list[str] = Field(min_length=1)
    scientific_status: ScientificStatus

    @field_validator("source_ids")
    @classmethod
    def source_ids_must_be_unique_nonempty(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("at least one source id is required")
        if len(normalized) != len(set(normalized)):
            raise ValueError("source ids must be unique")
        return normalized


class LocalSkyPosition(StrictSkyPlanningModel):
    target_id: str
    observed_at: datetime
    altitude_airless_deg: float = Field(ge=-90.0, le=90.0)
    altitude_apparent_deg: float = Field(ge=-90.0, le=90.0)
    azimuth_deg: float = Field(ge=0.0, lt=360.0)
    above_horizon_apparent: bool
    airmass: float | None = Field(default=None, gt=0.0)
    source_ids: list[str]
    scientific_status: ScientificStatus

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value


class MeteorShowerDefinition(StrictSkyPlanningModel):
    shower_id: str
    name: str
    radiant: FixedSkyTarget
    peak_time_utc: datetime | None = None
    theoretical_zhr: float | None = Field(default=None, ge=0.0)
    parent_body: str | None = None
    source_ids: list[str] = Field(min_length=1)

    @field_validator("peak_time_utc")
    @classmethod
    def peak_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("peak_time_utc must be timezone-aware")
        return value


class MeteorGeometryResult(StrictSkyPlanningModel):
    shower_id: str
    radiant_position: LocalSkyPosition
    radiant_elevation_factor: float = Field(ge=0.0, le=1.0)
    theoretical_zhr: float | None = Field(default=None, ge=0.0)
    expected_observed_rate: None = None
    scientific_status: ScientificStatus = ScientificStatus.INFERENCIA
    interpretation: str = (
        "Radiant elevation factor is geometric only. ZHR, when supplied, is an idealized shower descriptor; this result does not predict an observed meteor count."
    )
