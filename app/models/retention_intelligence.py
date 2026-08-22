from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.analytics_brain import AnalyticsPlatform
from app.models.metric_normalizer import MetricNormalizerPlan


RETENTION_INTELLIGENCE_VERSION = "retention-intelligence-v0.1"


class StrictRetentionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RetentionStatus(str, Enum):
    WAITING_FOR_RETENTION_DATA = "WAITING_FOR_RETENTION_DATA"
    RETENTION_CURVES_READY = "RETENTION_CURVES_READY"


class RetentionIntelligenceRequest(StrictRetentionModel):
    metrics: MetricNormalizerPlan


class RetentionInsight(StrictRetentionModel):
    platform: AnalyticsPlatform
    content_id: str
    point_count: int = Field(ge=2)
    first_10_percent_mean: float | None = Field(default=None, ge=0)
    midpoint_ratio: float | None = Field(default=None, ge=0)
    final_ratio: float | None = Field(default=None, ge=0)
    largest_drop_position_ratio: float | None = Field(default=None, ge=0, le=1)
    largest_drop_magnitude: float | None = Field(default=None, ge=0)
    causal_claim: bool = False
    recommendation: str | None = None

    @model_validator(mode="after")
    def validate_insight(self):
        if self.causal_claim:
            raise ValueError("F34 cannot make causal claims")
        if self.recommendation is not None:
            raise ValueError("F34 remains descriptive; recommendations belong later")
        return self


class RetentionIntelligencePlan(StrictRetentionModel):
    version: str = RETENTION_INTELLIGENCE_VERSION
    source_metric_normalizer_hash: str
    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    interpolates_missing_points: bool = False
    causal_claims: bool = False
    recommendations_generated: bool = False
    uses_llm: bool = False
    network_calls: int = 0
    auto_publication: bool = False

    status: RetentionStatus
    curve_count: int = Field(ge=0)
    insights: list[RetentionInsight]

    retention_intelligence_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.curve_count != len(self.insights):
            raise ValueError("curve_count mismatch")
        expected = (
            RetentionStatus.RETENTION_CURVES_READY
            if self.insights
            else RetentionStatus.WAITING_FOR_RETENTION_DATA
        )
        if self.status != expected:
            raise ValueError("status mismatch")
        if (
            not self.planning_only
            or self.interpolates_missing_points
            or self.causal_claims
            or self.recommendations_generated
            or self.uses_llm
            or self.network_calls != 0
            or self.auto_publication
        ):
            raise ValueError("F34 guardrail violation")
        return self
