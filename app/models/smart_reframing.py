from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astromedia import MediaType
from app.models.astronomical_tracker import AstronomicalTrackingPlan
from app.models.best_moment import BestMomentPlan
from app.models.cinematic_director import CompositionIntent, MotionIntent
from app.models.schema import VideoFitMode
from app.models.shot_quality import ShotQualityPlan
from app.models.video_base import VideoBasePlan
from app.models.visual_story_graph import VisualStoryGraph


SMART_REFRAMING_VERSION = "smart-reframing-v0.1"


class StrictReframingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ReframingSceneStatus(str, Enum):
    PLACEHOLDER_NOT_APPLICABLE = "PLACEHOLDER_NOT_APPLICABLE"
    FIT_PASSTHROUGH = "FIT_PASSTHROUGH"
    DYNAMIC_TRACKING = "DYNAMIC_TRACKING"
    DYNAMIC_TRACKING_PARTIAL = "DYNAMIC_TRACKING_PARTIAL"
    STATIC_SMARTFOCAL = "STATIC_SMARTFOCAL"
    STATIC_SAFE_CENTER = "STATIC_SAFE_CENTER"
    STATIC_F6_FOCAL = "STATIC_F6_FOCAL"


class FocalSource(str, Enum):
    F11_TRACKING = "F11_TRACKING"
    SMARTFOCAL_V01 = "SMARTFOCAL_V01"
    SMARTFOCAL_SAFE_CENTER = "SMARTFOCAL_SAFE_CENTER"
    F6_FOCAL = "F6_FOCAL"
    NONE = "NONE"


class SmartFocalHint(StrictReframingModel):
    scene_number: int = Field(ge=1)
    focal_x: float = Field(ge=0.0, le=1.0)
    focal_y: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    method: str = Field(min_length=1, max_length=200)


class CropGeometry(StrictReframingModel):
    crop_width_norm: float = Field(gt=0.0, le=1.0)
    crop_height_norm: float = Field(gt=0.0, le=1.0)
    target_aspect_ratio: float = Field(gt=0.0)


class ReframeKeyframe(StrictReframingModel):
    timestamp_s: float = Field(ge=0.0)

    subject_x: float | None = Field(default=None, ge=0.0, le=1.0)
    subject_y: float | None = Field(default=None, ge=0.0, le=1.0)

    focal_x: float = Field(ge=0.0, le=1.0)
    focal_y: float = Field(ge=0.0, le=1.0)

    crop_x: float = Field(ge=0.0, le=1.0)
    crop_y: float = Field(ge=0.0, le=1.0)
    crop_width: float = Field(gt=0.0, le=1.0)
    crop_height: float = Field(gt=0.0, le=1.0)

    focal_source: FocalSource

    @model_validator(mode="after")
    def validate_crop(self):
        if self.crop_x + self.crop_width > 1.000001:
            raise ValueError("crop exceeds right source edge")
        if self.crop_y + self.crop_height > 1.000001:
            raise ValueError("crop exceeds bottom source edge")
        return self


class SmartReframingRequest(StrictReframingModel):
    video_base: VideoBasePlan
    story_graph: VisualStoryGraph
    shot_quality: ShotQualityPlan
    best_moment: BestMomentPlan
    tracking: AstronomicalTrackingPlan
    smartfocal_hints: list[SmartFocalHint] = Field(default_factory=list)

    target_width: int = Field(default=1080, gt=0)
    target_height: int = Field(default=1920, gt=0)

    dead_zone_fraction: float = Field(default=0.04, ge=0.0, le=0.20)
    max_pan_speed_per_s: float = Field(default=0.18, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_hints(self):
        numbers = [hint.scene_number for hint in self.smartfocal_hints]
        if len(numbers) != len(set(numbers)):
            raise ValueError("only one SmartFocal hint is allowed per scene")
        return self


class ReframingScenePlan(StrictReframingModel):
    scene_number: int = Field(ge=1)
    node_id: str

    selected_media_id: str | None = None
    media_type: MediaType | None = None
    source_path: str | None = None

    fit_mode: VideoFitMode
    composition_intent: CompositionIntent
    motion_intent: MotionIntent

    status: ReframingSceneStatus
    focal_source: FocalSource

    execution_ready: bool
    review_required: bool

    source_width: int = Field(ge=0)
    source_height: int = Field(ge=0)
    source_rotation_deg: int

    window_start_s: float | None = Field(default=None, ge=0.0)
    window_end_s: float | None = Field(default=None, gt=0.0)

    smartfocal_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    smartfocal_method: str | None = None

    crop_geometry: CropGeometry | None = None
    keyframes: list[ReframeKeyframe] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scene(self):
        if self.status in {
            ReframingSceneStatus.PLACEHOLDER_NOT_APPLICABLE,
            ReframingSceneStatus.FIT_PASSTHROUGH,
        }:
            if self.crop_geometry is not None or self.keyframes:
                raise ValueError(
                    "placeholder/FIT passthrough cannot contain crop keyframes"
                )
        else:
            if self.crop_geometry is None:
                raise ValueError("reframed scene requires crop geometry")
            if not self.keyframes:
                raise ValueError("reframed scene requires keyframes")

        if (
            self.status == ReframingSceneStatus.DYNAMIC_TRACKING_PARTIAL
            and not self.review_required
        ):
            raise ValueError("partial tracking reframing must require review")

        if self.execution_ready and self.review_required:
            raise ValueError(
                "execution_ready and review_required cannot both be true"
            )

        return self


class ReframingStructuralChecks(StrictReframingModel):
    source_alignment: bool
    graph_hash_preserved: bool
    quality_hash_preserved: bool
    best_moment_hash_preserved: bool
    tracking_hash_preserved: bool
    material_identity_preserved: bool
    fit_mode_preserved: bool
    best_moment_window_preserved: bool
    smartfocal_fallback_contract_used: bool
    no_tracking_reexecution: bool


class SmartReframingPlan(StrictReframingModel):
    version: str = SMART_REFRAMING_VERSION
    subject: str

    source_plan_context_hash: str
    source_video_base_version: str
    source_story_graph_version: str
    source_story_graph_hash: str
    source_shot_quality_version: str
    source_shot_quality_hash: str
    source_best_moment_version: str
    source_best_moment_hash: str
    source_tracking_version: str
    source_tracking_hash: str

    target_width: int = 1080
    target_height: int = 1920
    target_aspect: str = "9:16"

    deterministic: bool = True
    reframing_phase: bool = True
    smartfocal_foundation_reused: bool = True
    precedence_policy: str = "F11_TRACKING__SMARTFOCAL__F6_FOCAL"
    smoothing_policy: str = "DEADZONE_EMA_SPEED_LIMIT_V01"
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_video: bool = False
    searches_material: bool = False
    changes_material_identity: bool = False
    changes_fit_mode: bool = False
    best_moment_search_triggered: bool = False
    tracking_reexecuted: bool = False
    smartfocal_analyzer_invocations: int = Field(default=0, ge=0)
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    placeholder_count: int = Field(ge=0)
    fit_passthrough_count: int = Field(ge=0)
    dynamic_tracking_count: int = Field(ge=0)
    dynamic_partial_count: int = Field(ge=0)
    static_smartfocal_count: int = Field(ge=0)
    static_safe_center_count: int = Field(ge=0)
    static_f6_focal_count: int = Field(ge=0)

    smartfocal_hint_count: int = Field(ge=0)
    smartfocal_accepted_count: int = Field(ge=0)
    smartfocal_rejected_count: int = Field(ge=0)

    execution_ready_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    keyframe_count: int = Field(ge=0)

    scenes: list[ReframingScenePlan]
    structural_checks: ReframingStructuralChecks
    reframing_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.target_width != 1080 or self.target_height != 1920:
            raise ValueError("F12 V0.1 target is fixed at 1080x1920")
        if self.target_aspect != "9:16":
            raise ValueError("F12 V0.1 target_aspect must be 9:16")
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count must equal scenes length")

        mapping = {
            ReframingSceneStatus.PLACEHOLDER_NOT_APPLICABLE:
                self.placeholder_count,
            ReframingSceneStatus.FIT_PASSTHROUGH:
                self.fit_passthrough_count,
            ReframingSceneStatus.DYNAMIC_TRACKING:
                self.dynamic_tracking_count,
            ReframingSceneStatus.DYNAMIC_TRACKING_PARTIAL:
                self.dynamic_partial_count,
            ReframingSceneStatus.STATIC_SMARTFOCAL:
                self.static_smartfocal_count,
            ReframingSceneStatus.STATIC_SAFE_CENTER:
                self.static_safe_center_count,
            ReframingSceneStatus.STATIC_F6_FOCAL:
                self.static_f6_focal_count,
        }

        for status, expected in mapping.items():
            actual = sum(scene.status == status for scene in self.scenes)
            if actual != expected:
                raise ValueError(f"{status.value} count mismatch")

        if sum(mapping.values()) != self.scene_count:
            raise ValueError("reframing status counts do not cover all scenes")

        actual_ready = sum(scene.execution_ready for scene in self.scenes)
        actual_review = sum(scene.review_required for scene in self.scenes)
        actual_keyframes = sum(len(scene.keyframes) for scene in self.scenes)

        if self.execution_ready_count != actual_ready:
            raise ValueError("execution_ready_count mismatch")
        if self.review_required_count != actual_review:
            raise ValueError("review_required_count mismatch")
        if self.keyframe_count != actual_keyframes:
            raise ValueError("keyframe_count mismatch")

        if (
            self.smartfocal_accepted_count
            + self.smartfocal_rejected_count
            > self.smartfocal_hint_count
        ):
            raise ValueError("SmartFocal consumed counts exceed hint count")

        checks = self.structural_checks
        if not all(
            (
                checks.source_alignment,
                checks.graph_hash_preserved,
                checks.quality_hash_preserved,
                checks.best_moment_hash_preserved,
                checks.tracking_hash_preserved,
                checks.material_identity_preserved,
                checks.fit_mode_preserved,
                checks.best_moment_window_preserved,
                checks.smartfocal_fallback_contract_used,
                checks.no_tracking_reexecution,
            )
        ):
            raise ValueError("all F12 structural checks must pass")

        if (
            self.uses_llm
            or self.gpu_required
            or self.renders_video
            or self.searches_material
            or self.changes_material_identity
            or self.changes_fit_mode
            or self.best_moment_search_triggered
            or self.tracking_reexecuted
            or self.smartfocal_analyzer_invocations != 0
            or self.auto_publication
        ):
            raise ValueError("F12 V0.1 guardrail violation")

        return self
