from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.shot_matching import ShotMatchingPlan
from app.models.visual_story_graph import VisualStoryGraph


TRANSITION_DIRECTOR_VERSION = "transition-director-v0.1"


class StrictTransitionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class TransitionStatus(str, Enum):
    PLACEHOLDER_PENDING_MEDIA = "PLACEHOLDER_PENDING_MEDIA"
    TRANSITION_PLAN_READY = "TRANSITION_PLAN_READY"


class TransitionType(str, Enum):
    CUT = "CUT"
    SOFT_DISSOLVE = "SOFT_DISSOLVE"
    FADE_TO_BLACK = "FADE_TO_BLACK"


class TransitionDirectorRequest(StrictTransitionModel):
    story_graph: VisualStoryGraph
    shot_matching: ShotMatchingPlan


class TransitionSpec(StrictTransitionModel):
    edge_id: str
    source_scene_number: int = Field(ge=1)
    target_scene_number: int = Field(ge=1)
    status: TransitionStatus
    transition_type: TransitionType
    duration_seconds: float = Field(ge=0.0, le=0.40)
    motivated_by_source_intent: bool = True
    execution_ready: bool
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_transition(self):
        if self.transition_type == TransitionType.CUT and self.duration_seconds != 0.0:
            raise ValueError("CUT duration must be zero")
        if self.status == TransitionStatus.PLACEHOLDER_PENDING_MEDIA and self.execution_ready:
            raise ValueError("placeholder transition cannot execute")
        if self.status == TransitionStatus.TRANSITION_PLAN_READY and not self.execution_ready:
            raise ValueError("ready transition must execute")
        return self


class TransitionDirectorPlan(StrictTransitionModel):
    version: str = TRANSITION_DIRECTOR_VERSION
    subject: str
    source_plan_context_hash: str
    source_story_graph_hash: str
    source_shot_matching_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_video: bool = False
    creates_flashy_transitions: bool = False
    searches_assets: bool = False
    auto_publication: bool = False

    transition_count: int = Field(ge=0)
    placeholder_pending_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)

    transitions: list[TransitionSpec]
    transition_director_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.transition_count != len(self.transitions):
            raise ValueError("transition_count mismatch")
        if self.placeholder_pending_count != sum(
            item.status == TransitionStatus.PLACEHOLDER_PENDING_MEDIA
            for item in self.transitions
        ):
            raise ValueError("placeholder_pending_count mismatch")
        if self.ready_count != sum(
            item.status == TransitionStatus.TRANSITION_PLAN_READY
            for item in self.transitions
        ):
            raise ValueError("ready_count mismatch")
        if self.placeholder_pending_count + self.ready_count != self.transition_count:
            raise ValueError("F21 statuses do not cover transitions")
        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.renders_video
            or self.creates_flashy_transitions
            or self.searches_assets
            or self.auto_publication
        ):
            raise ValueError("F21 guardrail violation")
        return self
