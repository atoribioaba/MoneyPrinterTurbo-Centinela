from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.analytics_brain import AnalyticsPlatform
from app.models.metric_normalizer import MetricNormalizerPlan


PERFORMANCE_SIGNALS_VERSION = "performance-signals-v0.1"


class StrictPerformanceSignalsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class PerformanceSignalStatus(str, Enum):
    WAITING_FOR_ANALYTICS_DATA = "WAITING_FOR_ANALYTICS_DATA"
    INSUFFICIENT_COHORT = "INSUFFICIENT_COHORT"
    COHORT_SIGNALS_READY = "COHORT_SIGNALS_READY"


class PerformanceSignalsRequest(StrictPerformanceSignalsModel):
    metrics: MetricNormalizerPlan
    minimum_cohort_size: int = Field(default=5, ge=3, le=100)


class ContentPerformanceSignal(StrictPerformanceSignalsModel):
    platform: AnalyticsPlatform
    content_id: str
    cohort_size: int = Field(ge=1)
    view_count: float | None = Field(default=None, ge=0)
    interaction_count: float | None = Field(default=None, ge=0)
    interaction_rate_per_view: float | None = Field(default=None, ge=0)
    view_percentile_within_cohort: float | None = Field(default=None, ge=0, le=1)
    interaction_rate_percentile_within_cohort: float | None = Field(default=None, ge=0, le=1)
    composite_score: float | None = None
    causal_claim: bool = False

    @model_validator(mode="after")
    def validate_signal(self):
        if self.composite_score is not None:
            raise ValueError("F33 V0.1 does not produce a composite score")
        if self.causal_claim:
            raise ValueError("F33 cannot make causal claims")
        return self


class PerformanceSignalsPlan(StrictPerformanceSignalsModel):
    version: str = PERFORMANCE_SIGNALS_VERSION
    source_metric_normalizer_hash: str
    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    cross_platform_ranking: bool = False
    composite_score_enabled: bool = False
    causal_claims: bool = False
    uses_llm: bool = False
    network_calls: int = 0
    auto_publication: bool = False

    status: PerformanceSignalStatus
    content_count: int = Field(ge=0)
    ready_signal_count: int = Field(ge=0)
    signals: list[ContentPerformanceSignal]

    performance_signals_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.content_count != len(self.signals):
            raise ValueError("content_count mismatch")
        if self.ready_signal_count != sum(
            item.view_percentile_within_cohort is not None
            or item.interaction_rate_percentile_within_cohort is not None
            for item in self.signals
        ):
            raise ValueError("ready_signal_count mismatch")
        if (
            not self.planning_only
            or self.cross_platform_ranking
            or self.composite_score_enabled
            or self.causal_claims
            or self.uses_llm
            or self.network_calls != 0
            or self.auto_publication
        ):
            raise ValueError("F33 guardrail violation")
        return self
