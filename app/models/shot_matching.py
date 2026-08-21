from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.color_science import ColorSciencePlan
from app.models.shot_quality import ShotQualityPlan
from app.models.visual_story_graph import VisualStoryGraph


SHOT_MATCHING_VERSION = "shot-matching-v0.1"


class StrictShotMatchingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ShotMatchStatus(str, Enum):
    PLACEHOLDER_PAIR_NOT_APPLICABLE = "PLACEHOLDER_PAIR_NOT_APPLICABLE"
    METRICS_UNAVAILABLE = "METRICS_UNAVAILABLE"
    MATCH_PLAN_READY = "MATCH_PLAN_READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ShotMatchingRequest(StrictShotMatchingModel):
    story_graph: VisualStoryGraph
    shot_quality: ShotQualityPlan
    color_science: ColorSciencePlan


class ShotMatchEdge(StrictShotMatchingModel):
    edge_id: str
    source_scene_number: int = Field(ge=1)
    target_scene_number: int = Field(ge=1)
    status: ShotMatchStatus

    source_y_avg: float | None = Field(default=None, ge=0.0, le=255.0)
    target_y_avg: float | None = Field(default=None, ge=0.0, le=255.0)
    exposure_offset_ev: float | None = Field(default=None, ge=-0.75, le=0.75)
    color_profile_continuity: str | None = None

    execution_ready: bool
    review_required: bool
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_edge(self):
        if self.status == ShotMatchStatus.MATCH_PLAN_READY:
            if (
                self.source_y_avg is None
                or self.target_y_avg is None
                or self.exposure_offset_ev is None
                or self.color_profile_continuity is None
            ):
                raise ValueError("ready shot match requires metrics and plan")
            if not self.execution_ready or self.review_required:
                raise ValueError("ready shot match readiness mismatch")
        else:
            if self.execution_ready:
                raise ValueError("non-ready shot match cannot execute")
        if self.review_required and self.status != ShotMatchStatus.REVIEW_REQUIRED:
            raise ValueError("review flag/status mismatch")
        return self


class ShotMatchingPlan(StrictShotMatchingModel):
    version: str = SHOT_MATCHING_VERSION
    subject: str
    source_plan_context_hash: str
    source_story_graph_hash: str
    source_quality_hash: str
    source_color_science_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_video: bool = False
    analyzes_new_frames: bool = False
    searches_material: bool = False
    changes_material_identity: bool = False
    auto_publication: bool = False

    edge_count: int = Field(ge=0)
    placeholder_pair_count: int = Field(ge=0)
    metrics_unavailable_count: int = Field(ge=0)
    match_ready_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)

    edges: list[ShotMatchEdge]
    shot_matching_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.edge_count != len(self.edges):
            raise ValueError("edge_count mismatch")
        mapping = {
            ShotMatchStatus.PLACEHOLDER_PAIR_NOT_APPLICABLE: self.placeholder_pair_count,
            ShotMatchStatus.METRICS_UNAVAILABLE: self.metrics_unavailable_count,
            ShotMatchStatus.MATCH_PLAN_READY: self.match_ready_count,
            ShotMatchStatus.REVIEW_REQUIRED: self.review_required_count,
        }
        for status, expected in mapping.items():
            if sum(edge.status == status for edge in self.edges) != expected:
                raise ValueError(f"{status.value} count mismatch")
        if sum(mapping.values()) != self.edge_count:
            raise ValueError("F20 statuses do not cover edges")
        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.renders_video
            or self.analyzes_new_frames
            or self.searches_material
            or self.changes_material_identity
            or self.auto_publication
        ):
            raise ValueError("F20 guardrail violation")
        return self
