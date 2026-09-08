from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.astronomy import ObserverContext, ScientificStatus


class StrictSmallBodyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SmallBodyObserverRequest(StrictSmallBodyModel):
    target_command: str = Field(min_length=1, max_length=256)
    observer: ObserverContext
    observed_at: datetime
    source_id: str = "jpl_horizons"

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value

    @field_validator("target_command")
    @classmethod
    def target_command_must_be_explicit(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("target command cannot be empty")
        if any(character in value for character in ("\r", "\n", "\x00")):
            raise ValueError("target command contains forbidden control characters")
        return value


class HorizonsQueryPlan(StrictSmallBodyModel):
    endpoint: str
    params: dict[str, str]
    source_id: str
    documentation_url: str
    source_note: str
    scientific_status: ScientificStatus = ScientificStatus.HECHO_VERIFICADO


class SmallBodyEphemerisProvenance(StrictSmallBodyModel):
    target_command: str
    query_time_utc: datetime
    retrieved_at_utc: datetime
    source_id: str
    api_version: str | None = None
    result_sha256: str
    scientific_status: ScientificStatus = ScientificStatus.HECHO_VERIFICADO

    @field_validator("query_time_utc", "retrieved_at_utc")
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ephemeris timestamps must be timezone-aware")
        return value
