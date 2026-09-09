from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.astronomy import ObserverContext, ScientificStatus


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
    activity_start_utc: datetime | None = None
    activity_end_utc: datetime | None = None
    radiant_epoch_utc: datetime | None = None
    radiant_drift_ra_deg_per_day: float | None = None
    radiant_drift_dec_deg_per_day: float | None = None
    theoretical_zhr: float | None = Field(default=None, ge=0.0)
    population_index: float | None = Field(default=None, gt=0.0)
    parent_body: str | None = None
    catalog_status: str | None = None
    source_ids: list[str] = Field(min_length=1)

    @field_validator(
        "peak_time_utc",
        "activity_start_utc",
        "activity_end_utc",
        "radiant_epoch_utc",
    )
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("meteor shower timestamps must be timezone-aware")
        return value

    @field_validator("source_ids")
    @classmethod
    def shower_source_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("meteor shower requires source ids")
        if len(normalized) != len(set(normalized)):
            raise ValueError("meteor shower source ids must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_activity_and_radiant_drift(self):
        if (
            self.activity_start_utc is not None
            and self.activity_end_utc is not None
            and self.activity_start_utc >= self.activity_end_utc
        ):
            raise ValueError("meteor shower activity start must precede activity end")

        has_drift = (
            self.radiant_drift_ra_deg_per_day is not None
            or self.radiant_drift_dec_deg_per_day is not None
        )
        if has_drift and self.radiant_epoch_utc is None:
            raise ValueError("radiant drift requires radiant_epoch_utc")
        return self


class MeteorGeometryResult(StrictSkyPlanningModel):
    shower_id: str
    radiant_position: LocalSkyPosition
    radiant_elevation_factor: float = Field(ge=0.0, le=1.0)
    theoretical_zhr: float | None = Field(default=None, ge=0.0)
    expected_observed_rate: None = None
    scientific_status: ScientificStatus = ScientificStatus.INFERENCIA
    interpretation: str = (
        "Radiant elevation factor is geometric only. ZHR, when supplied, is an "
        "idealized shower descriptor; this result does not predict an observed "
        "meteor count."
    )


class MeteorWindowRequest(StrictSkyPlanningModel):
    shower: MeteorShowerDefinition
    observer: ObserverContext
    start_utc: datetime
    end_utc: datetime
    step_minutes: int = Field(default=15, ge=5, le=60)

    @field_validator("start_utc", "end_utc")
    @classmethod
    def window_times_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("meteor planning window must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_window(self):
        if self.start_utc >= self.end_utc:
            raise ValueError("meteor planning start must precede end")
        if (self.end_utc - self.start_utc).total_seconds() > 72 * 3600:
            raise ValueError("meteor planning window cannot exceed 72 hours")
        return self


class MeteorWindowSample(StrictSkyPlanningModel):
    observed_at: datetime
    shower_active: bool
    radiant_position: LocalSkyPosition
    sun_altitude_deg: float = Field(ge=-90.0, le=90.0)
    moon_altitude_deg: float = Field(ge=-90.0, le=90.0)
    moon_illumination_fraction: float = Field(ge=0.0, le=1.0)
    moon_radiant_separation_deg: float = Field(ge=0.0, le=180.0)
    geometry_score: float = Field(ge=0.0, le=100.0)
    source_ids: list[str]
    scientific_status: ScientificStatus = ScientificStatus.INFERENCIA

    @field_validator("observed_at")
    @classmethod
    def sample_time_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("meteor sample time must be timezone-aware")
        return value


class MeteorWindowPlan(StrictSkyPlanningModel):
    shower_id: str
    samples: list[MeteorWindowSample] = Field(min_length=1)
    best_sample: MeteorWindowSample | None = None
    expected_observed_rate: None = None
    source_ids: list[str]
    scientific_status: ScientificStatus = ScientificStatus.INFERENCIA
    interpretation: str = (
        "This plan ranks local geometry, darkness and Moon interference only. "
        "It does not convert ZHR into a predicted observed meteor count and does "
        "not include weather unless evaluated separately by Observation Intelligence."
    )


class LandscapeWindowRequest(StrictSkyPlanningModel):
    target: FixedSkyTarget
    observer: ObserverContext
    start_utc: datetime
    end_utc: datetime
    step_minutes: int = Field(default=15, ge=5, le=60)
    minimum_target_altitude_deg: float = Field(default=10.0, ge=-10.0, le=90.0)
    maximum_sun_altitude_deg: float = Field(default=-12.0, ge=-30.0, le=0.0)
    minimum_moon_separation_deg: float | None = Field(default=None, ge=0.0, le=180.0)

    @field_validator("start_utc", "end_utc")
    @classmethod
    def landscape_times_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("landscape planning window must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_window(self):
        if self.start_utc >= self.end_utc:
            raise ValueError("landscape planning start must precede end")
        if (self.end_utc - self.start_utc).total_seconds() > 72 * 3600:
            raise ValueError("landscape planning window cannot exceed 72 hours")
        return self


class LandscapeWindowSample(StrictSkyPlanningModel):
    observed_at: datetime
    target_position: LocalSkyPosition
    sun_altitude_deg: float = Field(ge=-90.0, le=90.0)
    moon_altitude_deg: float = Field(ge=-90.0, le=90.0)
    moon_illumination_fraction: float = Field(ge=0.0, le=1.0)
    moon_target_separation_deg: float = Field(ge=0.0, le=180.0)
    eligible: bool
    blockers: list[str]
    geometry_score: float = Field(ge=0.0, le=100.0)
    source_ids: list[str]
    scientific_status: ScientificStatus = ScientificStatus.INFERENCIA

    @field_validator("observed_at")
    @classmethod
    def landscape_sample_time_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("landscape sample time must be timezone-aware")
        return value


class LandscapeWindowPlan(StrictSkyPlanningModel):
    target_id: str
    samples: list[LandscapeWindowSample] = Field(min_length=1)
    best_sample: LandscapeWindowSample | None = None
    source_ids: list[str]
    scientific_status: ScientificStatus = ScientificStatus.INFERENCIA
    interpretation: str = (
        "This is a geometric landscape-sky window. Weather, real horizon obstructions, "
        "light pollution and foreground composition remain independent evidence."
    )
