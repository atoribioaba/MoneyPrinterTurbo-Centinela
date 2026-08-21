from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astromedia import MediaType
from app.models.cinematic_director import (
    CinematicPace,
    CompositionIntent,
    MotionIntent,
)
from app.models.schema import VideoFitMode
from app.models.smart_reframing import SmartReframingPlan
from app.models.video_base import VideoBasePlan
from app.models.visual_story_graph import VisualStoryGraph


SMART_KEN_BURNS_VERSION = "smart-ken-burns-v0.1"


class StrictKenBurnsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class KenBurnsMotionType(str, Enum):
    HOLD = "HOLD"
    PUSH_IN = "PUSH_IN"
    PULL_BACK = "PULL_BACK"
    CONTROLLED_REVEAL = "CONTROLLED_REVEAL"


class KenBurnsSceneStatus(str, Enum):
    PLACEHOLDER_NOT_APPLICABLE = "PLACEHOLDER_NOT_APPLICABLE"
    VIDEO_NOT_APPLICABLE = "VIDEO_NOT_APPLICABLE"
    FIT_STATIC_HOLD = "FIT_STATIC_HOLD"
    STATIC_HOLD = "STATIC_HOLD"
    PUSH_IN_PLANNED = "PUSH_IN_PLANNED"
    PULL_BACK_PLANNED = "PULL_BACK_PLANNED"
    CONTROLLED_REVEAL_PLANNED = "CONTROLLED_REVEAL_PLANNED"
    REFRAMING_REVIEW_REQUIRED = "REFRAMING_REVIEW_REQUIRED"


class KenBurnsKeyframe(StrictKenBurnsModel):
    timestamp_s: float = Field(ge=0.0)

    crop_x: float = Field(ge=0.0, le=1.0)
    crop_y: float = Field(ge=0.0, le=1.0)
    crop_width: float = Field(gt=0.0, le=1.0)
    crop_height: float = Field(gt=0.0, le=1.0)

    focal_x: float = Field(ge=0.0, le=1.0)
    focal_y: float = Field(ge=0.0, le=1.0)

    zoom_factor: float = Field(ge=1.0, le=1.20)

    @model_validator(mode="after")
    def validate_crop(self):
        if self.crop_x + self.crop_width > 1.000001:
            raise ValueError("Ken Burns crop exceeds right source edge")
        if self.crop_y + self.crop_height > 1.000001:
            raise ValueError("Ken Burns crop exceeds bottom source edge")
        return self


class SmartKenBurnsRequest(StrictKenBurnsModel):
    video_base: VideoBasePlan
    story_graph: VisualStoryGraph
    reframing: SmartReframingPlan

    max_zoom_delta: float = Field(default=0.09, ge=0.0, le=0.12)
    reveal_pan_fraction: float = Field(default=0.035, ge=0.0, le=0.08)


class KenBurnsScenePlan(StrictKenBurnsModel):
    scene_number: int = Field(ge=1)
    node_id: str

    selected_media_id: str | None = None
    media_type: MediaType | None = None
    source_path: str | None = None

    duration_seconds: float = Field(gt=0.0)

    fit_mode: VideoFitMode
    pace: CinematicPace
    intensity: float = Field(ge=0.0, le=1.0)
    composition_intent: CompositionIntent
    motion_intent: MotionIntent

    status: KenBurnsSceneStatus
    motion_type: KenBurnsMotionType

    execution_ready: bool
    review_required: bool

    zoom_delta: float = Field(default=0.0, ge=0.0, le=0.12)
    easing: str = "ease_in_out_sine"

    keyframes: list[KenBurnsKeyframe] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scene(self):
        no_crop_statuses = {
            KenBurnsSceneStatus.PLACEHOLDER_NOT_APPLICABLE,
            KenBurnsSceneStatus.VIDEO_NOT_APPLICABLE,
            KenBurnsSceneStatus.FIT_STATIC_HOLD,
            KenBurnsSceneStatus.REFRAMING_REVIEW_REQUIRED,
        }

        if self.status in no_crop_statuses and self.keyframes:
            raise ValueError(
                "non-motion/non-crop F13 scene cannot contain keyframes"
            )

        crop_statuses = {
            KenBurnsSceneStatus.STATIC_HOLD,
            KenBurnsSceneStatus.PUSH_IN_PLANNED,
            KenBurnsSceneStatus.PULL_BACK_PLANNED,
            KenBurnsSceneStatus.CONTROLLED_REVEAL_PLANNED,
        }

        if self.status in crop_statuses:
            if len(self.keyframes) != 2:
                raise ValueError(
                    "cover-image F13 scene requires exactly two keyframes"
                )
            if self.keyframes[0].timestamp_s != 0.0:
                raise ValueError("first F13 keyframe must start at 0s")
            if abs(
                self.keyframes[-1].timestamp_s - self.duration_seconds
            ) > 1e-6:
                raise ValueError(
                    "last F13 keyframe must equal scene duration"
                )

        if self.status == KenBurnsSceneStatus.STATIC_HOLD:
            if self.motion_type != KenBurnsMotionType.HOLD:
                raise ValueError("STATIC_HOLD requires HOLD motion")
            if self.zoom_delta != 0.0:
                raise ValueError("STATIC_HOLD cannot contain zoom")

        if self.status == KenBurnsSceneStatus.PUSH_IN_PLANNED:
            if self.motion_type != KenBurnsMotionType.PUSH_IN:
                raise ValueError("PUSH_IN status mismatch")

        if self.status == KenBurnsSceneStatus.PULL_BACK_PLANNED:
            if self.motion_type != KenBurnsMotionType.PULL_BACK:
                raise ValueError("PULL_BACK status mismatch")

        if self.status == KenBurnsSceneStatus.CONTROLLED_REVEAL_PLANNED:
            if self.motion_type != KenBurnsMotionType.CONTROLLED_REVEAL:
                raise ValueError("CONTROLLED_REVEAL status mismatch")

        if self.execution_ready and self.review_required:
            raise ValueError(
                "execution_ready and review_required cannot both be true"
            )

        return self


class KenBurnsStructuralChecks(StrictKenBurnsModel):
    source_alignment: bool
    reframing_hash_preserved: bool
    material_identity_preserved: bool
    fit_mode_preserved: bool
    target_geometry_preserved: bool
    image_only_motion: bool
    no_reframing_reexecution: bool
    no_tracking_reexecution: bool
    no_smartfocal_reexecution: bool


class SmartKenBurnsPlan(StrictKenBurnsModel):
    version: str = SMART_KEN_BURNS_VERSION
    subject: str

    source_plan_context_hash: str
    source_video_base_version: str
    source_story_graph_version: str
    source_story_graph_hash: str
    source_reframing_version: str
    source_reframing_hash: str

    target_width: int
    target_height: int
    target_aspect: str

    deterministic: bool = True
    ken_burns_phase: bool = True
    normalized_geometry: bool = True
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_video: bool = False
    searches_material: bool = False
    changes_material_identity: bool = False
    changes_fit_mode: bool = False
    best_moment_search_triggered: bool = False
    tracking_reexecuted: bool = False
    smartfocal_reexecuted: bool = False
    reframing_reexecuted: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    placeholder_count: int = Field(ge=0)
    video_not_applicable_count: int = Field(ge=0)
    fit_static_hold_count: int = Field(ge=0)
    static_hold_count: int = Field(ge=0)
    push_in_count: int = Field(ge=0)
    pull_back_count: int = Field(ge=0)
    controlled_reveal_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)

    motion_scene_count: int = Field(ge=0)
    execution_ready_count: int = Field(ge=0)
    keyframe_count: int = Field(ge=0)

    scenes: list[KenBurnsScenePlan]
    structural_checks: KenBurnsStructuralChecks

    ken_burns_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count must equal scenes length")

        mapping = {
            KenBurnsSceneStatus.PLACEHOLDER_NOT_APPLICABLE:
                self.placeholder_count,
            KenBurnsSceneStatus.VIDEO_NOT_APPLICABLE:
                self.video_not_applicable_count,
            KenBurnsSceneStatus.FIT_STATIC_HOLD:
                self.fit_static_hold_count,
            KenBurnsSceneStatus.STATIC_HOLD:
                self.static_hold_count,
            KenBurnsSceneStatus.PUSH_IN_PLANNED:
                self.push_in_count,
            KenBurnsSceneStatus.PULL_BACK_PLANNED:
                self.pull_back_count,
            KenBurnsSceneStatus.CONTROLLED_REVEAL_PLANNED:
                self.controlled_reveal_count,
            KenBurnsSceneStatus.REFRAMING_REVIEW_REQUIRED:
                self.review_required_count,
        }

        for status, expected in mapping.items():
            actual = sum(scene.status == status for scene in self.scenes)
            if actual != expected:
                raise ValueError(f"{status.value} count mismatch")

        if sum(mapping.values()) != self.scene_count:
            raise ValueError("F13 status counts do not cover all scenes")

        expected_motion = (
            self.push_in_count
            + self.pull_back_count
            + self.controlled_reveal_count
        )
        if self.motion_scene_count != expected_motion:
            raise ValueError("motion_scene_count mismatch")

        actual_ready = sum(scene.execution_ready for scene in self.scenes)
        actual_keys = sum(len(scene.keyframes) for scene in self.scenes)

        if self.execution_ready_count != actual_ready:
            raise ValueError("execution_ready_count mismatch")
        if self.keyframe_count != actual_keys:
            raise ValueError("keyframe_count mismatch")

        checks = self.structural_checks
        if not all(
            (
                checks.source_alignment,
                checks.reframing_hash_preserved,
                checks.material_identity_preserved,
                checks.fit_mode_preserved,
                checks.target_geometry_preserved,
                checks.image_only_motion,
                checks.no_reframing_reexecution,
                checks.no_tracking_reexecution,
                checks.no_smartfocal_reexecution,
            )
        ):
            raise ValueError("all F13 structural checks must pass")

        if (
            self.uses_llm
            or self.gpu_required
            or self.renders_video
            or self.searches_material
            or self.changes_material_identity
            or self.changes_fit_mode
            or self.best_moment_search_triggered
            or self.tracking_reexecuted
            or self.smartfocal_reexecuted
            or self.reframing_reexecuted
            or self.auto_publication
        ):
            raise ValueError("F13 V0.1 guardrail violation")

        return self
