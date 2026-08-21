from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import AstronomyVideoPlan
from app.models.visual_story_graph import VisualStoryGraph


ASTRONOMY_MOTION_GRAPHICS_VERSION = "astronomy-motion-graphics-v0.1"


class StrictMotionGraphicsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class MotionGraphicKind(str, Enum):
    OBJECT_LABEL = "OBJECT_LABEL"
    SCIENTIFIC_CLAIM_CALLOUT = "SCIENTIFIC_CLAIM_CALLOUT"


class MotionGraphicAnchor(str, Enum):
    TOP_SAFE = "TOP_SAFE"
    LOWER_THIRD = "LOWER_THIRD"
    SIDE_CARD = "SIDE_CARD"


class MotionGraphicAnimation(str, Enum):
    FADE_IN_HOLD_FADE_OUT = "FADE_IN_HOLD_FADE_OUT"
    GENTLE_SLIDE_IN_HOLD_FADE_OUT = "GENTLE_SLIDE_IN_HOLD_FADE_OUT"


class MotionGraphicCue(StrictMotionGraphicsModel):
    cue_id: str
    scene_number: int = Field(ge=1)
    kind: MotionGraphicKind
    text: str = Field(min_length=1, max_length=400)

    scientific_status: ScientificStatus
    fact_ids: list[str] = Field(default_factory=list)

    anchor: MotionGraphicAnchor
    animation: MotionGraphicAnimation

    normalized_start: float = Field(ge=0.0, le=1.0)
    normalized_end: float = Field(ge=0.0, le=1.0)

    object_screen_coordinates_used: bool = False
    trajectory_invented: bool = False
    numeric_value_invented: bool = False

    review_required: bool

    @model_validator(mode="after")
    def validate_cue(self):
        if self.normalized_end <= self.normalized_start:
            raise ValueError("motion graphic end must be after start")
        if (
            self.scientific_status == ScientificStatus.HECHO_VERIFICADO
            and self.kind == MotionGraphicKind.SCIENTIFIC_CLAIM_CALLOUT
            and not self.fact_ids
        ):
            raise ValueError("verified claim cue requires fact_ids")
        if (
            self.object_screen_coordinates_used
            or self.trajectory_invented
            or self.numeric_value_invented
        ):
            raise ValueError("F16 cannot invent spatial/scientific data")
        return self


class MotionGraphicsScene(StrictMotionGraphicsModel):
    scene_number: int = Field(ge=1)
    node_id: str
    cue_count: int = Field(ge=0)
    cues: list[MotionGraphicCue] = Field(default_factory=list)
    review_required: bool

    @model_validator(mode="after")
    def validate_count(self):
        if self.cue_count != len(self.cues):
            raise ValueError("cue_count mismatch")
        return self


class MotionGraphicsStructuralChecks(StrictMotionGraphicsModel):
    plan_graph_alignment: bool
    explicit_objects_only: bool
    plan_claims_only: bool
    verified_claim_fact_ids_preserved: bool
    no_invented_coordinates: bool
    no_invented_trajectories: bool
    no_invented_numeric_values: bool
    scientific_status_preserved: bool


class AstronomyMotionGraphicsPlan(StrictMotionGraphicsModel):
    version: str = ASTRONOMY_MOTION_GRAPHICS_VERSION
    subject: str
    source_plan_context_hash: str
    source_story_graph_version: str
    source_story_graph_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_graphics: bool = False
    downloads_assets: bool = False
    searches_web: bool = False
    tracks_objects: bool = False
    computes_astronomy: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    cue_count: int = Field(ge=0)
    object_label_count: int = Field(ge=0)
    claim_callout_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)

    scenes: list[MotionGraphicsScene]
    structural_checks: MotionGraphicsStructuralChecks

    motion_graphics_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count mismatch")

        cues = [cue for scene in self.scenes for cue in scene.cues]
        if self.cue_count != len(cues):
            raise ValueError("cue_count mismatch")
        if self.object_label_count != sum(
            cue.kind == MotionGraphicKind.OBJECT_LABEL for cue in cues
        ):
            raise ValueError("object_label_count mismatch")
        if self.claim_callout_count != sum(
            cue.kind == MotionGraphicKind.SCIENTIFIC_CLAIM_CALLOUT
            for cue in cues
        ):
            raise ValueError("claim_callout_count mismatch")
        if self.review_required_count != sum(
            scene.review_required for scene in self.scenes
        ):
            raise ValueError("review_required_count mismatch")

        checks = self.structural_checks
        if not all(checks.model_dump().values()):
            raise ValueError("all F16 structural checks must pass")

        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.renders_graphics
            or self.downloads_assets
            or self.searches_web
            or self.tracks_objects
            or self.computes_astronomy
            or self.auto_publication
        ):
            raise ValueError("F16 guardrail violation")

        return self
