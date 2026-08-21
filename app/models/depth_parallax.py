from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astromedia import MediaType
from app.models.smart_ken_burns import SmartKenBurnsPlan
from app.models.visual_story_graph import VisualStoryGraph


DEPTH_PARALLAX_VERSION = "depth-parallax-v0.1"


class StrictDepthParallaxModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DepthParallaxStatus(str, Enum):
    PLACEHOLDER_NOT_APPLICABLE = "PLACEHOLDER_NOT_APPLICABLE"
    VIDEO_NOT_APPLICABLE = "VIDEO_NOT_APPLICABLE"
    DEPTH_MAP_REQUIRED = "DEPTH_MAP_REQUIRED"
    DEPTH_MAP_READY = "DEPTH_MAP_READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class DepthMapHint(StrictDepthParallaxModel):
    scene_number: int = Field(ge=1)
    source_media_id: str
    depth_map_path: str = Field(min_length=1)
    source_match_verified: bool = True
    near_is_high: bool = True


class DepthParallaxRequest(StrictDepthParallaxModel):
    story_graph: VisualStoryGraph
    ken_burns: SmartKenBurnsPlan
    depth_maps: list[DepthMapHint] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_hints(self):
        numbers = [item.scene_number for item in self.depth_maps]
        if len(numbers) != len(set(numbers)):
            raise ValueError("depth map hints must be unique by scene")
        return self


class DepthParallaxScene(StrictDepthParallaxModel):
    scene_number: int = Field(ge=1)
    node_id: str
    selected_media_id: str | None = None
    media_type: MediaType | None = None

    status: DepthParallaxStatus
    depth_map_path: str | None = None

    execution_ready: bool
    review_required: bool

    layer_count: int = Field(default=0, ge=0, le=5)
    max_parallax_shift_fraction: float = Field(default=0.0, ge=0.0, le=0.04)
    easing: str = "ease_in_out_sine"

    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scene(self):
        if self.status == DepthParallaxStatus.DEPTH_MAP_READY:
            if not self.depth_map_path:
                raise ValueError("ready depth scene requires depth map path")
            if not self.execution_ready or self.review_required:
                raise ValueError("ready depth scene readiness mismatch")
            if self.layer_count < 2:
                raise ValueError("ready depth scene requires at least two layers")
        else:
            if self.execution_ready:
                raise ValueError("non-ready depth scene cannot execute")
            if self.layer_count != 0 or self.max_parallax_shift_fraction != 0.0:
                raise ValueError("non-ready depth scene cannot contain parallax")
        if self.review_required and self.status != DepthParallaxStatus.REVIEW_REQUIRED:
            raise ValueError("review flag/status mismatch")
        return self


class DepthParallaxStructuralChecks(StrictDepthParallaxModel):
    source_alignment: bool
    graph_hash_preserved: bool
    ken_burns_hash_preserved: bool
    image_only_depth: bool
    explicit_depth_map_only: bool
    no_depth_inference: bool
    no_model_download: bool
    no_render: bool


class DepthParallaxPlan(StrictDepthParallaxModel):
    version: str = DEPTH_PARALLAX_VERSION
    subject: str

    source_plan_context_hash: str
    source_story_graph_version: str
    source_story_graph_hash: str
    source_ken_burns_version: str
    source_ken_burns_hash: str

    recommended_candidate: str = "Depth Anything V2 Small"
    candidate_license: str = "Apache-2.0 (Small model)"
    candidate_decision: str = "ALTERNATIVA_OSS_RECOMENDADA_PENDING_LOCAL_BENCHMARK"

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_video: bool = False
    runs_depth_model: bool = False
    downloads_models: bool = False
    searches_web: bool = False
    changes_material_identity: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    placeholder_count: int = Field(ge=0)
    video_not_applicable_count: int = Field(ge=0)
    depth_map_required_count: int = Field(ge=0)
    depth_map_ready_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)

    scenes: list[DepthParallaxScene]
    structural_checks: DepthParallaxStructuralChecks

    depth_parallax_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count mismatch")

        expected = {
            DepthParallaxStatus.PLACEHOLDER_NOT_APPLICABLE: self.placeholder_count,
            DepthParallaxStatus.VIDEO_NOT_APPLICABLE: self.video_not_applicable_count,
            DepthParallaxStatus.DEPTH_MAP_REQUIRED: self.depth_map_required_count,
            DepthParallaxStatus.DEPTH_MAP_READY: self.depth_map_ready_count,
            DepthParallaxStatus.REVIEW_REQUIRED: self.review_required_count,
        }
        for status, count in expected.items():
            if sum(scene.status == status for scene in self.scenes) != count:
                raise ValueError(f"{status.value} count mismatch")
        if sum(expected.values()) != self.scene_count:
            raise ValueError("F18 statuses do not cover scenes")

        if not all(self.structural_checks.model_dump().values()):
            raise ValueError("all F18 structural checks must pass")

        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.renders_video
            or self.runs_depth_model
            or self.downloads_models
            or self.searches_web
            or self.changes_material_identity
            or self.auto_publication
        ):
            raise ValueError("F18 guardrail violation")
        return self
