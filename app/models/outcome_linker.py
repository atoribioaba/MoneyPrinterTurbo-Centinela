from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.analytics_brain import AnalyticsPlatform
from app.models.content_feature_registry import ContentFeatureRegistryPlan
from app.models.metric_normalizer import CanonicalMetric, MetricNormalizerPlan


OUTCOME_LINKER_VERSION = "outcome-linker-v0.1"


class StrictOutcomeLinkerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class OutcomeLinkerStatus(str, Enum):
    WAITING_FOR_BOUND_CONTENT_ANALYTICS = "WAITING_FOR_BOUND_CONTENT_ANALYTICS"
    JOINED_OUTCOMES_READY = "JOINED_OUTCOMES_READY"


class OutcomeLinkerRequest(StrictOutcomeLinkerModel):
    features: ContentFeatureRegistryPlan
    metrics: MetricNormalizerPlan


class LinkedOutcome(StrictOutcomeLinkerModel):
    platform: AnalyticsPlatform
    content_id: str
    snapshot_id: str
    canonical_metric: CanonicalMetric
    value: float
    observed_at_utc: datetime
    source_native_metric_name: str
    source_metric_normalizer_hash: str


class FeatureOutcomeRecord(StrictOutcomeLinkerModel):
    platform: AnalyticsPlatform
    content_id: str
    snapshot_id: str
    features: dict[str, float]
    outcome_count: int = Field(ge=1)
    outcomes: list[LinkedOutcome]

    @model_validator(mode="after")
    def validate_record(self):
        if self.outcome_count != len(self.outcomes):
            raise ValueError("outcome_count mismatch")
        if not self.features:
            raise ValueError("joined record requires features")
        return self


class OutcomeLinkerPlan(StrictOutcomeLinkerModel):
    version: str = OUTCOME_LINKER_VERSION
    source_content_feature_registry_hash: str
    source_metric_normalizer_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    joins_native_only_metrics: bool = False
    cross_platform_join: bool = False
    interpolates_observations: bool = False
    uses_llm: bool = False
    network_calls: int = 0
    database_writes: int = 0
    auto_publication: bool = False

    status: OutcomeLinkerStatus
    record_count: int = Field(ge=0)
    joined_outcome_count: int = Field(ge=0)
    records: list[FeatureOutcomeRecord]

    outcome_linker_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.record_count != len(self.records):
            raise ValueError("record_count mismatch")
        if self.joined_outcome_count != sum(item.outcome_count for item in self.records):
            raise ValueError("joined_outcome_count mismatch")
        expected = (
            OutcomeLinkerStatus.JOINED_OUTCOMES_READY
            if self.records
            else OutcomeLinkerStatus.WAITING_FOR_BOUND_CONTENT_ANALYTICS
        )
        if self.status != expected:
            raise ValueError("status mismatch")
        if (
            not self.planning_only
            or self.joins_native_only_metrics
            or self.cross_platform_join
            or self.interpolates_observations
            or self.uses_llm
            or self.network_calls != 0
            or self.database_writes != 0
            or self.auto_publication
        ):
            raise ValueError("F37 guardrail violation")
        return self
