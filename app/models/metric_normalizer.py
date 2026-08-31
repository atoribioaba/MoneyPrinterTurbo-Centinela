from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.analytics_brain import (
    AnalyticsBrainPlan,
    NativeMetricObservation,
)


METRIC_NORMALIZER_VERSION = "metric-normalizer-v0.1"


class StrictMetricNormalizerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CanonicalMetric(str, Enum):
    VIEW_COUNT = "VIEW_COUNT"
    LIKE_COUNT = "LIKE_COUNT"
    COMMENT_COUNT = "COMMENT_COUNT"
    SHARE_COUNT = "SHARE_COUNT"
    SAVE_COUNT = "SAVE_COUNT"
    FOLLOWERS_GAINED = "FOLLOWERS_GAINED"
    AVG_VIEW_DURATION_SECONDS = "AVG_VIEW_DURATION_SECONDS"
    AVG_VIEW_PERCENTAGE = "AVG_VIEW_PERCENTAGE"
    AUDIENCE_WATCH_RATIO = "AUDIENCE_WATCH_RATIO"


class NormalizationStatus(str, Enum):
    NORMALIZED_VERIFIED = "NORMALIZED_VERIFIED"
    NATIVE_ONLY = "NATIVE_ONLY"


class MetricNormalizerRequest(StrictMetricNormalizerModel):
    analytics: AnalyticsBrainPlan


class NormalizedMetricObservation(StrictMetricNormalizerModel):
    source: NativeMetricObservation
    canonical_metric: CanonicalMetric | None = None
    normalization_status: NormalizationStatus
    mapping_basis: str
    cross_platform_equivalence_assumed: bool = False

    @model_validator(mode="after")
    def validate_mapping(self):
        if self.normalization_status == NormalizationStatus.NORMALIZED_VERIFIED:
            if self.canonical_metric is None:
                raise ValueError("verified normalization requires canonical metric")
        elif self.canonical_metric is not None:
            raise ValueError("native-only observation cannot contain canonical metric")
        if self.cross_platform_equivalence_assumed:
            raise ValueError("F32 cannot assume cross-platform equivalence")
        return self


class MetricNormalizerPlan(StrictMetricNormalizerModel):
    version: str = METRIC_NORMALIZER_VERSION
    source_analytics_hash: str
    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    network_calls: int = 0
    api_calls: int = 0
    cross_platform_equivalence_assumed: bool = False
    auto_publication: bool = False

    observation_count: int = Field(ge=0)
    normalized_count: int = Field(ge=0)
    native_only_count: int = Field(ge=0)
    observations: list[NormalizedMetricObservation]
    status: str

    metric_normalizer_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.observation_count != len(self.observations):
            raise ValueError("observation_count mismatch")
        if self.normalized_count != sum(
            item.normalization_status == NormalizationStatus.NORMALIZED_VERIFIED
            for item in self.observations
        ):
            raise ValueError("normalized_count mismatch")
        if self.native_only_count != self.observation_count - self.normalized_count:
            raise ValueError("native_only_count mismatch")
        expected = "NORMALIZATION_COMPLETE" if self.observations else "WAITING_FOR_ANALYTICS_DATA"
        if self.status != expected:
            raise ValueError("status mismatch")
        if (
            not self.planning_only
            or self.uses_llm
            or self.network_calls != 0
            or self.api_calls != 0
            or self.cross_platform_equivalence_assumed
            or self.auto_publication
        ):
            raise ValueError("F32 guardrail violation")
        return self
