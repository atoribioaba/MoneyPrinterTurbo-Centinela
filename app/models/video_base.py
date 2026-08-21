from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astronomy_director import AstronomyVideoPlan
from app.models.astromedia import MediaType, Provider, Rights
from app.models.material_selection import MaterialSelectionPlan, SelectionStatus
from app.models.schema import VideoFitMode


VIDEO_BASE_VERSION = "video-base-v0.1"
VIDEO_BASE_WIDTH = 1080
VIDEO_BASE_HEIGHT = 1920
VIDEO_BASE_FPS = 30


class StrictVideoBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class VideoBaseRenderMode(str, Enum):
    REVIEW_PARTIAL = "REVIEW_PARTIAL"
    CLEAN_BASE = "CLEAN_BASE"


class VideoBaseRenderAction(str, Enum):
    VIDEO = "VIDEO"
    IMAGE = "IMAGE"
    PLACEHOLDER = "PLACEHOLDER"


class VideoBaseBlockCode(str, Enum):
    NO_ADEQUATE_MEDIA = "NO_ADEQUATE_MEDIA"
    AI_RECREATION_REQUIRED = "AI_RECREATION_REQUIRED"
    MISSING_SELECTION = "MISSING_SELECTION"
    UNKNOWN_MEDIA_ID = "UNKNOWN_MEDIA_ID"
    INACTIVE_MEDIA = "INACTIVE_MEDIA"
    NON_RENDERABLE_MEDIA = "NON_RENDERABLE_MEDIA"
    MISSING_SOURCE = "MISSING_SOURCE"
    SOURCE_PATH_MISMATCH = "SOURCE_PATH_MISMATCH"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    INVALID_MEDIA = "INVALID_MEDIA"
    SOURCE_TOO_SHORT = "SOURCE_TOO_SHORT"


class ResourceClass(str, Enum):
    LIGHT = "LIGHT"
    MEDIUM = "MEDIUM"
    HEAVY = "HEAVY"
    EXCLUSIVE = "EXCLUSIVE"


class VideoBasePlanRequest(StrictVideoBaseModel):
    plan: AstronomyVideoPlan
    materials: MaterialSelectionPlan
    render_mode: VideoBaseRenderMode = VideoBaseRenderMode.REVIEW_PARTIAL
    default_fit_mode: VideoFitMode = VideoFitMode.fit
    focal_x: float = Field(default=0.5, ge=0.0, le=1.0)
    focal_y: float = Field(default=0.5, ge=0.0, le=1.0)
    requested_codec: Literal["h264_nvenc", "libx264"] = "h264_nvenc"


class VideoBaseRenderRequest(VideoBasePlanRequest):
    keep_segments: bool = True


class VideoBaseScenePlan(StrictVideoBaseModel):
    scene_number: int = Field(ge=1)
    scene_key: str
    duration_seconds: float = Field(gt=0.0)
    visual_requirement: str
    narration: str

    material_selection_status: SelectionStatus
    render_action: VideoBaseRenderAction

    selected_media_id: str | None = None
    source_path: str | None = None
    media_type: MediaType | None = None
    provider: Provider | None = None
    rights_status: Rights | None = None
    publication_eligible: bool | None = None

    source_width: int = Field(default=0, ge=0)
    source_height: int = Field(default=0, ge=0)
    source_rotation_deg: int = 0
    source_duration_seconds: float = Field(default=0.0, ge=0.0)
    source_start_s: float = Field(default=0.0, ge=0.0)
    source_fingerprint: str | None = None

    fit_mode: VideoFitMode = VideoFitMode.fit
    focal_x: float = Field(default=0.5, ge=0.0, le=1.0)
    focal_y: float = Field(default=0.5, ge=0.0, le=1.0)

    renderable: bool
    clean_base_eligible: bool
    placeholder: bool = False
    placeholder_reason: VideoBaseBlockCode | None = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_action_contract(self):
        if self.placeholder:
            if self.render_action != VideoBaseRenderAction.PLACEHOLDER:
                raise ValueError("placeholder scene must use PLACEHOLDER action")
            if self.placeholder_reason is None:
                raise ValueError("placeholder scene requires placeholder_reason")
            if self.clean_base_eligible:
                raise ValueError("placeholder scene cannot be CLEAN_BASE eligible")
        else:
            if self.render_action == VideoBaseRenderAction.PLACEHOLDER:
                raise ValueError("non-placeholder scene cannot use PLACEHOLDER action")
            if not self.renderable:
                raise ValueError("non-placeholder scene must be renderable")
            if not self.source_path or not self.selected_media_id or self.media_type is None:
                raise ValueError("renderable scene requires source metadata")
        return self


class VideoBasePlan(StrictVideoBaseModel):
    version: str = VIDEO_BASE_VERSION
    subject: str
    source_plan_context_hash: str
    source_selector_version: str
    render_mode: VideoBaseRenderMode

    output_width: int = VIDEO_BASE_WIDTH
    output_height: int = VIDEO_BASE_HEIGHT
    fps: int = VIDEO_BASE_FPS
    audio_enabled: bool = False

    requested_codec: Literal["h264_nvenc", "libx264"] = "h264_nvenc"
    fallback_codec: Literal["libx264"] = "libx264"

    scene_count: int = Field(ge=1)
    unresolved_count: int = Field(ge=0)
    placeholder_count: int = Field(ge=0)
    clean_base_eligible: bool
    source_materials_publication_ready: bool
    scenes: list[VideoBaseScenePlan]
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan_contract(self):
        if self.output_width != VIDEO_BASE_WIDTH or self.output_height != VIDEO_BASE_HEIGHT:
            raise ValueError("Video Base V0.1 is fixed at 1080x1920")
        if self.fps != VIDEO_BASE_FPS:
            raise ValueError("Video Base V0.1 is fixed at 30 fps")
        if self.audio_enabled:
            raise ValueError("Video Base V0.1 must not contain audio")
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count must equal scenes length")
        actual_placeholders = sum(scene.placeholder for scene in self.scenes)
        if self.placeholder_count != actual_placeholders:
            raise ValueError("placeholder_count mismatch")
        if self.clean_base_eligible != all(scene.clean_base_eligible for scene in self.scenes):
            raise ValueError("clean_base_eligible mismatch")
        if self.render_mode == VideoBaseRenderMode.CLEAN_BASE and not self.clean_base_eligible:
            raise ValueError("CLEAN_BASE plan cannot contain non-eligible scenes")
        return self


class RenderSceneManifest(StrictVideoBaseModel):
    scene_number: int
    material_selection_status: SelectionStatus
    render_action: VideoBaseRenderAction
    selected_media_id: str | None = None
    provider: Provider | None = None
    rights_status: Rights | None = None
    source_path: str | None = None
    source_fingerprint: str | None = None
    source_duration_seconds: float = 0.0
    source_start_s: float = 0.0
    requested_duration_seconds: float
    rendered_duration_seconds: float
    fit_mode: VideoFitMode
    focal_x: float
    focal_y: float
    source_rotation_deg: int
    placeholder: bool
    placeholder_reason: VideoBaseBlockCode | None = None
    segment_path: str
    segment_sha256: str


class VideoBaseRenderManifest(StrictVideoBaseModel):
    version: str = VIDEO_BASE_VERSION
    task_id: str
    render_mode: VideoBaseRenderMode
    output_width: int
    output_height: int
    fps: int
    requested_codec: str
    effective_codec: str
    codec_fallback: bool
    codec_fallback_reason: str | None = None
    ffmpeg_binary: str
    nvenc_probe_success: bool | None = None
    concat_mode: Literal["copy", "reencode"]
    ffmpeg_version: str
    scene_count: int
    placeholder_count: int
    expected_duration_seconds: float
    rendered_duration_seconds: float
    final_video_path: str
    final_video_sha256: str
    final_video_codec: str
    final_pixel_format: str
    final_audio_stream_count: int
    scenes: list[RenderSceneManifest]
    generated_at_utc: datetime


class VideoBaseRenderResult(StrictVideoBaseModel):
    task_id: str
    output_dir: str
    video_path: str
    manifest_path: str
    requested_codec: str
    effective_codec: str
    codec_fallback: bool
    concat_mode: Literal["copy", "reencode"]
    duration_seconds: float
    scene_count: int
    placeholder_count: int
