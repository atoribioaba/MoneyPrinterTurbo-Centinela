from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astronomy import ScientificStatus


class StrictObservationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EvidenceKind(str, Enum):
    MEASURED = "measured"
    FORECAST = "forecast"
    MAP_DERIVED = "map_derived"
    INFERRED = "inferred"


class ObservationObjectClass(str, Enum):
    GENERAL = "general"
    PLANETARY = "planetary"
    LUNAR = "lunar"
    DEEP_SKY = "deep_sky"
    MILKY_WAY = "milky_way"
    METEOR = "meteor"
    COMET = "comet"


class WeatherSnapshot(StrictObservationModel):
    source_id: str
    valid_at: datetime
    retrieved_at: datetime
    evidence_kind: EvidenceKind = EvidenceKind.FORECAST
    model_name: str | None = None
    model_run_at: datetime | None = None

    temperature_c: float | None = None
    relative_humidity_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    dew_point_c: float | None = None

    cloud_cover_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    cloud_low_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    cloud_mid_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    cloud_high_percent: float | None = Field(default=None, ge=0.0, le=100.0)

    seeing_arcsec: float | None = Field(default=None, gt=0.0)
    transparency_percent: float | None = Field(default=None, ge=0.0, le=100.0)

    wind_speed_kph: float | None = Field(default=None, ge=0.0)
    wind_gust_kph: float | None = Field(default=None, ge=0.0)
    precipitation_probability_percent: float | None = Field(
        default=None, ge=0.0, le=100.0
    )


class SkyQualityContext(StrictObservationModel):
    source_id: str
    evidence_kind: EvidenceKind
    bortle_class: int | None = Field(default=None, ge=1, le=9)
    sqm_mag_arcsec2: float | None = Field(default=None, ge=10.0, le=30.0)

    @model_validator(mode="after")
    def require_sky_quality_value(self):
        if self.bortle_class is None and self.sqm_mag_arcsec2 is None:
            raise ValueError("sky quality requires bortle_class or sqm_mag_arcsec2")
        return self


class ObservabilityRequest(StrictObservationModel):
    object_class: ObservationObjectClass = ObservationObjectClass.GENERAL
    target_altitude_deg: float = Field(ge=-90.0, le=90.0)
    sun_altitude_deg: float = Field(ge=-90.0, le=90.0)
    moon_altitude_deg: float | None = Field(default=None, ge=-90.0, le=90.0)
    moon_target_separation_deg: float | None = Field(default=None, ge=0.0, le=180.0)
    moon_illumination_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    weather: WeatherSnapshot | None = None
    sky_quality: SkyQualityContext | None = None


class ScoreComponent(StrictObservationModel):
    name: str
    score: float = Field(ge=0.0, le=100.0)
    weight: float = Field(gt=0.0)
    rationale: str
    scientific_status: ScientificStatus = ScientificStatus.INFERENCIA


class ObservabilityResult(StrictObservationModel):
    score: float | None = Field(default=None, ge=0.0, le=100.0)
    grade: str
    completeness_percent: float = Field(ge=0.0, le=100.0)
    airmass: float | None = Field(default=None, gt=0.0)
    components: list[ScoreComponent]
    missing_inputs: list[str]
    scientific_status: ScientificStatus = ScientificStatus.INFERENCIA
    publication_note: str = (
        "Derived observing guidance. Forecasts and map-derived inputs are not "
        "astronomical facts and must retain their own source/timestamp provenance."
    )
