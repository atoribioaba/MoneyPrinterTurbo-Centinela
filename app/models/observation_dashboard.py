from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictDashboardModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DashboardEvidence(StrictDashboardModel):
    source_id: str
    evidence_kind: str
    valid_at: datetime | None = None
    retrieved_at: datetime | None = None
    stale: bool | None = None

    @field_validator("valid_at", "retrieved_at")
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("dashboard timestamps must be timezone-aware")
        return value


class DashboardMetric(StrictDashboardModel):
    metric_id: str
    label: str
    value_text: str
    state_text: str
    rationale: str
    source_ids: list[str] = Field(default_factory=list)
    available: bool = True


class ObservationDashboard(StrictDashboardModel):
    title: str
    grade: str
    score_text: str
    completeness_text: str
    completeness_percent: float = Field(ge=0.0, le=100.0)
    attention_required: bool
    attention_reasons: list[str] = Field(default_factory=list)
    metrics: list[DashboardMetric]
    evidence: list[DashboardEvidence]
    missing_inputs: list[str]
    framing_summary: str | None = None
    mosaic_summary: str | None = None
    sampling_summary: str | None = None
    scientific_label: str = "INFERENCIA"
    disclaimer: str = (
        "Observability is derived guidance, not a guaranteed observing outcome. "
        "The interface must display missing/stale inputs and source timestamps."
    )
