from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.cinematic_director import CinematicMood
from app.models.depth_parallax import DepthParallaxPlan
from app.models.visual_story_graph import VisualStoryGraph


COLOR_SCIENCE_VERSION = "color-science-v0.1"


class StrictColorScienceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ColorScienceStatus(str, Enum):
    PLACEHOLDER_NOT_APPLICABLE = "PLACEHOLDER_NOT_APPLICABLE"
    GRADE_PLAN_READY = "GRADE_PLAN_READY"


class ColorProfile(str, Enum):
    MYSTERIOUS_NEUTRAL_COOL = "MYSTERIOUS_NEUTRAL_COOL"
    CONTEMPLATIVE_NATURAL = "CONTEMPLATIVE_NATURAL"
    DISCOVERY_CLEAN = "DISCOVERY_CLEAN"
    AWE_CONTROLLED_CONTRAST = "AWE_CONTROLLED_CONTRAST"
    RELEASE_WARM_NEUTRAL = "RELEASE_WARM_NEUTRAL"
    AFTERGLOW_GENTLE = "AFTERGLOW_GENTLE"


class ColorScienceRequest(StrictColorScienceModel):
    story_graph: VisualStoryGraph
    depth_parallax: DepthParallaxPlan


class ColorScienceScene(StrictColorScienceModel):
    scene_number: int = Field(ge=1)
    node_id: str
    mood: CinematicMood
    status: ColorScienceStatus

    profile: ColorProfile | None = None
    saturation_scale: float | None = Field(default=None, ge=0.75, le=1.10)
    contrast_scale: float | None = Field(default=None, ge=0.85, le=1.15)
    highlight_rolloff: float | None = Field(default=None, ge=0.0, le=0.25)
    shadow_lift: float | None = Field(default=None, ge=-0.05, le=0.05)
    white_balance_bias: str | None = None

    preserve_astronomy_color: bool = True
    avoid_clipping: bool = True
    avoid_oversaturation: bool = True

    @model_validator(mode="after")
    def validate_scene(self):
        params = (
            self.profile,
            self.saturation_scale,
            self.contrast_scale,
            self.highlight_rolloff,
            self.shadow_lift,
            self.white_balance_bias,
        )
        if self.status == ColorScienceStatus.PLACEHOLDER_NOT_APPLICABLE:
            if any(value is not None for value in params):
                raise ValueError("placeholder color scene cannot contain grade")
        else:
            if any(value is None for value in params):
                raise ValueError("ready color scene requires complete grade plan")
        return self


class ColorSciencePlan(StrictColorScienceModel):
    version: str = COLOR_SCIENCE_VERSION
    subject: str
    source_plan_context_hash: str
    source_story_graph_hash: str
    source_depth_parallax_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_video: bool = False
    analyzes_pixels: bool = False
    applies_lut: bool = False
    downloads_luts: bool = False
    searches_web: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    placeholder_count: int = Field(ge=0)
    grade_ready_count: int = Field(ge=0)

    scenes: list[ColorScienceScene]
    color_science_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count mismatch")
        if self.placeholder_count != sum(
            scene.status == ColorScienceStatus.PLACEHOLDER_NOT_APPLICABLE
            for scene in self.scenes
        ):
            raise ValueError("placeholder_count mismatch")
        if self.grade_ready_count != sum(
            scene.status == ColorScienceStatus.GRADE_PLAN_READY
            for scene in self.scenes
        ):
            raise ValueError("grade_ready_count mismatch")
        if self.placeholder_count + self.grade_ready_count != self.scene_count:
            raise ValueError("F19 statuses do not cover scenes")
        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.renders_video
            or self.analyzes_pixels
            or self.applies_lut
            or self.downloads_luts
            or self.searches_web
            or self.auto_publication
        ):
            raise ValueError("F19 guardrail violation")
        return self
