from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.observation import EvidenceKind


class StrictSkyQualityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SkyQualitySourceMode(str, Enum):
    """How the sky-quality value was obtained.

    The mode is intentionally explicit because an SQM meter reading, a human
    Bortle classification and a map-derived estimate are different evidence
    classes and must never be silently interchanged.
    """

    SQM_METER = "sqm_meter"
    MANUAL_BORTLE = "manual_bortle"
    MAP_DERIVED_SQM = "map_derived_sqm"
    MAP_DERIVED_BORTLE = "map_derived_bortle"


class SkyQualityEvidenceRecord(StrictSkyQualityModel):
    source_id: str
    source_mode: SkyQualitySourceMode
    evidence_kind: EvidenceKind

    latitude_deg: float = Field(ge=-90.0, le=90.0)
    longitude_deg: float = Field(ge=-180.0, le=180.0)
    retrieved_at: datetime
    observed_at: datetime | None = None

    sqm_mag_arcsec2: float | None = Field(default=None, ge=10.0, le=30.0)
    bortle_class: int | None = Field(default=None, ge=1, le=9)

    instrument_model: str | None = None
    instrument_id: str | None = None
    calibration_reference: str | None = None

    dataset_id: str | None = None
    dataset_version: str | None = None
    dataset_period: str | None = None
    derivation_method: str | None = None

    @field_validator(
        "source_id",
        "instrument_model",
        "instrument_id",
        "calibration_reference",
        "dataset_id",
        "dataset_version",
        "dataset_period",
        "derivation_method",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("retrieved_at", "observed_at")
    @classmethod
    def timestamps_must_be_timezone_aware(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("sky-quality timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_provenance_contract(self):
        if not self.source_id:
            raise ValueError("source_id cannot be empty")
        if self.sqm_mag_arcsec2 is None and self.bortle_class is None:
            raise ValueError("sky-quality evidence requires SQM or Bortle data")

        if self.source_mode == SkyQualitySourceMode.SQM_METER:
            if self.evidence_kind != EvidenceKind.MEASURED:
                raise ValueError("SQM meter evidence must be classified as measured")
            if self.sqm_mag_arcsec2 is None:
                raise ValueError("SQM meter evidence requires sqm_mag_arcsec2")
            if self.observed_at is None:
                raise ValueError("SQM meter evidence requires observed_at")

        elif self.source_mode == SkyQualitySourceMode.MANUAL_BORTLE:
            if self.evidence_kind != EvidenceKind.INFERRED:
                raise ValueError(
                    "manual Bortle classification must be classified as inferred"
                )
            if self.bortle_class is None:
                raise ValueError("manual Bortle evidence requires bortle_class")
            if self.observed_at is None:
                raise ValueError("manual Bortle evidence requires observed_at")

        elif self.source_mode in {
            SkyQualitySourceMode.MAP_DERIVED_SQM,
            SkyQualitySourceMode.MAP_DERIVED_BORTLE,
        }:
            if self.evidence_kind != EvidenceKind.MAP_DERIVED:
                raise ValueError("map sky-quality evidence must be map_derived")
            if not self.dataset_id or not self.dataset_period:
                raise ValueError(
                    "map-derived sky quality requires dataset_id and dataset_period"
                )
            if self.source_mode == SkyQualitySourceMode.MAP_DERIVED_SQM:
                if self.sqm_mag_arcsec2 is None:
                    raise ValueError("map-derived SQM evidence requires SQM data")
            if self.source_mode == SkyQualitySourceMode.MAP_DERIVED_BORTLE:
                if self.bortle_class is None:
                    raise ValueError("map-derived Bortle evidence requires Bortle data")

        return self


class SkyQualityIngestionResult(StrictSkyQualityModel):
    source_id: str
    evidence_kind: EvidenceKind
    sqm_mag_arcsec2: float | None = None
    bortle_class: int | None = None
    observed_at: datetime | None = None
    retrieved_at: datetime
    warnings: list[str] = Field(default_factory=list)
    provenance_summary: str
