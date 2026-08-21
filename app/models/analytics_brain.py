from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


ANALYTICS_BRAIN_VERSION = "analytics-brain-v0.1"


class StrictAnalyticsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AnalyticsPlatform(str, Enum):
    YOUTUBE = "YOUTUBE"
    INSTAGRAM = "INSTAGRAM"
    TIKTOK = "TIKTOK"
    OTHER = "OTHER"


class AnalyticsSourceType(str, Enum):
    OFFICIAL_API = "OFFICIAL_API"
    CREATOR_EXPORT = "CREATOR_EXPORT"
    MANUAL_ENTRY = "MANUAL_ENTRY"
    PUBLIC_API = "PUBLIC_API"
    SYNTHETIC_TEST = "SYNTHETIC_TEST"


class AnalyticsSemanticConfidence(str, Enum):
    VERIFIED_PLATFORM_SEMANTICS = "VERIFIED_PLATFORM_SEMANTICS"
    SOURCE_NATIVE_ONLY = "SOURCE_NATIVE_ONLY"
    MANUAL_SEMANTIC_LABEL = "MANUAL_SEMANTIC_LABEL"


class MetricValueType(str, Enum):
    COUNT = "COUNT"
    RATIO = "RATIO"
    PERCENT = "PERCENT"
    SECONDS = "SECONDS"
    MINUTES = "MINUTES"
    CURRENCY = "CURRENCY"
    OTHER = "OTHER"


class NativeMetricObservation(StrictAnalyticsModel):
    platform: AnalyticsPlatform
    content_id: str = Field(min_length=1, max_length=256)
    native_metric_name: str = Field(min_length=1, max_length=128)
    value: float
    value_type: MetricValueType
    observed_at_utc: datetime
    source_type: AnalyticsSourceType
    source_ref: str | None = Field(default=None, max_length=1024)
    semantic_confidence: AnalyticsSemanticConfidence
    position_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    estimated: bool = False

    @model_validator(mode="after")
    def validate_observation(self):
        if self.value_type in {MetricValueType.COUNT, MetricValueType.SECONDS, MetricValueType.MINUTES}:
            if self.value < 0:
                raise ValueError("non-negative metric required")
        if self.value_type == MetricValueType.PERCENT and not 0 <= self.value <= 100:
            raise ValueError("percent must be 0..100")
        if self.value_type == MetricValueType.RATIO and self.value < 0:
            raise ValueError("ratio must be non-negative")
        return self


class AnalyticsBrainRequest(StrictAnalyticsModel):
    observations: list[NativeMetricObservation] = Field(default_factory=list)


class AnalyticsBrainPlan(StrictAnalyticsModel):
    version: str = ANALYTICS_BRAIN_VERSION
    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    storage_candidate: str = "SQLite"
    storage_candidate_classification: str = "OPEN_SOURCE + 100 % GRATUITA"
    storage_candidate_license: str = "Public Domain"
    alternative_olap_candidate: str = "DuckDB"
    alternative_olap_license: str = "MIT"
    storage_writes: int = 0

    api_calls: int = 0
    network_calls: int = 0
    credentials_required: bool = False
    uses_llm: bool = False
    gpu_required: bool = False
    auto_publication: bool = False

    observation_count: int = Field(ge=0)
    platform_count: int = Field(ge=0)
    content_count: int = Field(ge=0)
    observations: list[NativeMetricObservation]

    status: str
    analytics_brain_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.observation_count != len(self.observations):
            raise ValueError("observation_count mismatch")
        if self.platform_count != len({item.platform for item in self.observations}):
            raise ValueError("platform_count mismatch")
        if self.content_count != len({(item.platform, item.content_id) for item in self.observations}):
            raise ValueError("content_count mismatch")
        expected = "READY_FOR_NORMALIZATION" if self.observations else "WAITING_FOR_ANALYTICS_DATA"
        if self.status != expected:
            raise ValueError("status mismatch")
        if (
            not self.planning_only
            or self.storage_writes != 0
            or self.api_calls != 0
            or self.network_calls != 0
            or self.credentials_required
            or self.uses_llm
            or self.gpu_required
            or self.auto_publication
        ):
            raise ValueError("F31 guardrail violation")
        return self
