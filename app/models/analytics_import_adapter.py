from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.analytics_brain import (
    AnalyticsBrainRequest,
    AnalyticsPlatform,
    AnalyticsSemanticConfidence,
    AnalyticsSourceType,
    NativeMetricObservation,
)

ANALYTICS_IMPORT_ADAPTER_VERSION = "analytics-import-adapter-v0.1"


class StrictAnalyticsImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AnalyticsImportFormat(str, Enum):
    CSV = "CSV"
    JSON = "JSON"


class AnalyticsImportStatus(str, Enum):
    WAITING_FOR_IMPORT_DATA = "WAITING_FOR_IMPORT_DATA"
    IMPORT_READY = "IMPORT_READY"


class AnalyticsImportRequest(StrictAnalyticsImportModel):
    format: AnalyticsImportFormat = AnalyticsImportFormat.CSV
    payload_text: str = ""
    default_platform: AnalyticsPlatform | None = None
    default_source_type: AnalyticsSourceType = AnalyticsSourceType.CREATOR_EXPORT
    default_semantic_confidence: AnalyticsSemanticConfidence = (
        AnalyticsSemanticConfidence.SOURCE_NATIVE_ONLY
    )


class AnalyticsImportPlan(StrictAnalyticsImportModel):
    version: str = ANALYTICS_IMPORT_ADAPTER_VERSION
    deterministic: bool = True
    adapter_only: bool = True
    resource_class: str = "LIGHT"

    network_calls: int = 0
    api_calls: int = 0
    database_writes: int = 0
    credentials_required: bool = False
    uses_llm: bool = False
    auto_publication: bool = False

    status: AnalyticsImportStatus
    row_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    observations: list[NativeMetricObservation]
    analytics_request: AnalyticsBrainRequest
    analytics_import_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.observation_count != len(self.observations):
            raise ValueError("observation mismatch")
        if self.analytics_request.observations != self.observations:
            raise ValueError("analytics request mismatch")
        if self.row_count != self.observation_count:
            raise ValueError("V0.1 requires one observation per row")

        expected_status = (
            AnalyticsImportStatus.IMPORT_READY
            if self.observations
            else AnalyticsImportStatus.WAITING_FOR_IMPORT_DATA
        )
        if self.status != expected_status:
            raise ValueError("status mismatch")

        if (
            not self.deterministic
            or not self.adapter_only
            or self.network_calls != 0
            or self.api_calls != 0
            or self.database_writes != 0
            or self.credentials_required
            or self.uses_llm
            or self.auto_publication
        ):
            raise ValueError("F55 guardrail violation")
        return self
