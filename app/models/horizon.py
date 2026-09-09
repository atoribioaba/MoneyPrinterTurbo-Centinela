from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.astronomy import ScientificStatus


class StrictHorizonModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class HorizonPoint(StrictHorizonModel):
    azimuth_deg: float = Field(ge=0.0, lt=360.0)
    altitude_deg: float = Field(ge=-10.0, le=90.0)


class HorizonProfile(StrictHorizonModel):
    profile_id: str
    points: list[HorizonPoint] = Field(min_length=2, max_length=720)
    source_ids: list[str] = Field(min_length=1)
    scientific_status: ScientificStatus = ScientificStatus.NO_VERIFICADO

    @field_validator("profile_id")
    @classmethod
    def profile_id_must_be_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("horizon profile_id cannot be empty")
        return value

    @field_validator("source_ids")
    @classmethod
    def source_ids_must_be_unique_nonempty(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("horizon profile requires source ids")
        if len(normalized) != len(set(normalized)):
            raise ValueError("horizon profile source ids must be unique")
        return normalized

    @model_validator(mode="after")
    def points_must_have_unique_azimuths(self):
        azimuths = [round(item.azimuth_deg, 9) for item in self.points]
        if len(azimuths) != len(set(azimuths)):
            raise ValueError("horizon profile azimuths must be unique")
        return self
