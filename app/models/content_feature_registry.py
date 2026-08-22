from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.analytics_brain import AnalyticsPlatform
from app.models.astronomy_director import AstronomyVideoPlan
from app.models.visual_story_graph import VisualStoryGraph


CONTENT_FEATURE_REGISTRY_VERSION = "content-feature-registry-v0.1"


class StrictContentFeatureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ContentBindingStatus(str, Enum):
    WAITING_FOR_CONTENT_BINDING = "WAITING_FOR_CONTENT_BINDING"
    BOUND_TO_CONTENT = "BOUND_TO_CONTENT"


class ContentBinding(StrictContentFeatureModel):
    platform: AnalyticsPlatform
    content_id: str = Field(min_length=1, max_length=256)


class ContentFeatureValue(StrictContentFeatureModel):
    feature_name: str = Field(min_length=1, max_length=128)
    value: float
    unit: str | None = Field(default=None, max_length=64)
    provenance: list[str] = Field(min_length=1, max_length=8)


class ContentFeatureRegistryRequest(StrictContentFeatureModel):
    plan: AstronomyVideoPlan
    story_graph: VisualStoryGraph
    binding: ContentBinding | None = None


class ContentFeatureSnapshot(StrictContentFeatureModel):
    snapshot_id: str
    source_plan_context_hash: str
    source_story_graph_hash: str
    platform: AnalyticsPlatform | None = None
    content_id: str | None = None
    binding_status: ContentBindingStatus

    feature_count: int = Field(ge=1)
    features: list[ContentFeatureValue]

    @model_validator(mode="after")
    def validate_snapshot(self):
        if self.feature_count != len(self.features):
            raise ValueError("feature_count mismatch")

        names = [item.feature_name for item in self.features]
        if len(names) != len(set(names)):
            raise ValueError("feature names must be unique")

        if self.binding_status == ContentBindingStatus.BOUND_TO_CONTENT:
            if self.platform is None or self.content_id is None:
                raise ValueError("bound snapshot requires platform and content_id")
        else:
            if self.platform is not None or self.content_id is not None:
                raise ValueError("unbound snapshot cannot carry platform/content_id")

        return self


class ContentFeatureRegistryPlan(StrictContentFeatureModel):
    version: str = CONTENT_FEATURE_REGISTRY_VERSION
    subject: str
    source_plan_context_hash: str
    source_story_graph_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    stores_creative_text: bool = False
    analyzes_pixels: bool = False
    uses_llm: bool = False
    network_calls: int = 0
    database_writes: int = 0
    auto_publication: bool = False

    snapshot_count: int = Field(ge=1)
    bound_snapshot_count: int = Field(ge=0)
    status: ContentBindingStatus
    snapshots: list[ContentFeatureSnapshot]

    content_feature_registry_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.snapshot_count != len(self.snapshots):
            raise ValueError("snapshot_count mismatch")
        if self.bound_snapshot_count != sum(
            item.binding_status == ContentBindingStatus.BOUND_TO_CONTENT
            for item in self.snapshots
        ):
            raise ValueError("bound_snapshot_count mismatch")

        expected = (
            ContentBindingStatus.BOUND_TO_CONTENT
            if self.bound_snapshot_count == self.snapshot_count
            else ContentBindingStatus.WAITING_FOR_CONTENT_BINDING
        )
        if self.status != expected:
            raise ValueError("status mismatch")

        if (
            not self.planning_only
            or self.stores_creative_text
            or self.analyzes_pixels
            or self.uses_llm
            or self.network_calls != 0
            or self.database_writes != 0
            or self.auto_publication
        ):
            raise ValueError("F36 guardrail violation")
        return self
