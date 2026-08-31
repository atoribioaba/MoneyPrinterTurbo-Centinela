from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astromedia import MediaType
from app.models.shot_quality import ShotQualityPlan


MEDIA_MINING_VERSION = "media-mining-v0.1"


class StrictMediaMiningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class MediaMiningStatus(str, Enum):
    PLACEHOLDER_NOT_APPLICABLE = "PLACEHOLDER_NOT_APPLICABLE"
    IMAGE_SINGLE_SHOT = "IMAGE_SINGLE_SHOT"
    VIDEO_DETECTION_REQUIRED = "VIDEO_DETECTION_REQUIRED"
    SOURCE_ANALYSIS_FAILED = "SOURCE_ANALYSIS_FAILED"


class MediaMiningRequest(StrictMediaMiningModel):
    shot_quality: ShotQualityPlan


class MediaMiningScene(StrictMediaMiningModel):
    scene_number: int = Field(ge=1)
    source_path: str | None = None
    media_type: MediaType | None = None
    placeholder: bool

    status: MediaMiningStatus
    detector: str | None = None
    scene_detection_required: bool = False
    execution_ready: bool = False
    split_video_requested: bool = False
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scene(self):
        if self.execution_ready:
            raise ValueError("F27 V0.1 never auto-executes media mining")
        if self.split_video_requested:
            raise ValueError("F27 V0.1 never splits source video")
        if self.status == MediaMiningStatus.VIDEO_DETECTION_REQUIRED:
            if self.media_type != MediaType.VIDEO:
                raise ValueError("video detection requires VIDEO media")
            if not self.source_path:
                raise ValueError("video detection requires source_path")
            if self.detector != "AdaptiveDetector":
                raise ValueError("F27 V0.1 uses AdaptiveDetector candidate")
            if not self.scene_detection_required:
                raise ValueError("video detection status requires detection")
        else:
            if self.detector is not None or self.scene_detection_required:
                raise ValueError("non-video-detection scene cannot request detector")
        return self


class MediaMiningPlan(StrictMediaMiningModel):
    version: str = MEDIA_MINING_VERSION
    subject: str
    source_plan_context_hash: str
    source_quality_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    candidate_tool: str = "PySceneDetect"
    candidate_reference_version: str = "0.7.1"
    candidate_license: str = "BSD-3-Clause"
    candidate_detector: str = "AdaptiveDetector"

    uses_llm: bool = False
    gpu_required: bool = False
    scenedetect_invocations: int = 0
    analyzes_video: bool = False
    splits_video: bool = False
    downloads_dependencies: bool = False
    modifies_sources: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    placeholder_count: int = Field(ge=0)
    image_single_shot_count: int = Field(ge=0)
    video_detection_required_count: int = Field(ge=0)
    analysis_failed_count: int = Field(ge=0)
    scenes: list[MediaMiningScene]

    media_mining_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count mismatch")

        counts = {
            MediaMiningStatus.PLACEHOLDER_NOT_APPLICABLE: self.placeholder_count,
            MediaMiningStatus.IMAGE_SINGLE_SHOT: self.image_single_shot_count,
            MediaMiningStatus.VIDEO_DETECTION_REQUIRED: self.video_detection_required_count,
            MediaMiningStatus.SOURCE_ANALYSIS_FAILED: self.analysis_failed_count,
        }
        for status, expected in counts.items():
            if sum(scene.status == status for scene in self.scenes) != expected:
                raise ValueError(f"{status.value} count mismatch")
        if sum(counts.values()) != self.scene_count:
            raise ValueError("F27 statuses do not cover all scenes")

        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.scenedetect_invocations != 0
            or self.analyzes_video
            or self.splits_video
            or self.downloads_dependencies
            or self.modifies_sources
            or self.auto_publication
        ):
            raise ValueError("F27 guardrail violation")
        return self
