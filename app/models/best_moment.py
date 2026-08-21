from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astromedia import MediaType
from app.models.shot_quality import ShotQualityPlan
from app.models.video_base import VideoBasePlan
from app.models.visual_story_graph import VisualStoryGraph


BEST_MOMENT_VERSION = "best-moment-v0.1"


class StrictBestMomentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class BestMomentStatus(str, Enum):
    SELECTED = "SELECTED"
    PLACEHOLDER_NOT_APPLICABLE = "PLACEHOLDER_NOT_APPLICABLE"
    STATIC_IMAGE = "STATIC_IMAGE"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"


class BestMomentRequest(StrictBestMomentModel):
    video_base: VideoBasePlan
    story_graph: VisualStoryGraph
    shot_quality: ShotQualityPlan
    max_candidates: int = Field(default=9, ge=3, le=21)


class BestMomentCandidate(StrictBestMomentModel):
    candidate_index: int = Field(ge=1)
    window_start_s: float = Field(ge=0.0)
    window_end_s: float = Field(gt=0.0)
    sample_time_s: float = Field(ge=0.0)

    blur_metric: float = Field(ge=0.0)
    luma_span: float = Field(ge=0.0, le=255.0)
    y_min: float = Field(ge=0.0, le=255.0)
    y_max: float = Field(ge=0.0, le=255.0)
    y_avg: float = Field(ge=0.0, le=255.0)

    sharpness_relative: float = Field(ge=0.0, le=1.0)
    luma_range_score: float = Field(ge=0.0, le=1.0)
    temporal_score: float = Field(ge=0.0, le=1.0)


class BestMomentSceneResult(StrictBestMomentModel):
    scene_number: int = Field(ge=1)
    node_id: str
    selected_media_id: str | None = None
    media_type: MediaType | None = None
    source_path: str | None = None

    status: BestMomentStatus
    source_duration_seconds: float = Field(ge=0.0)
    requested_duration_seconds: float = Field(gt=0.0)
    original_start_s: float = Field(ge=0.0)

    selected_start_s: float | None = Field(default=None, ge=0.0)
    selected_end_s: float | None = Field(default=None, gt=0.0)
    selected_sample_time_s: float | None = Field(default=None, ge=0.0)
    selected_score: float | None = Field(default=None, ge=0.0, le=1.0)

    baseline_shot_quality_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    candidates: list[BestMomentCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scene(self):
        if self.status == BestMomentStatus.SELECTED:
            if self.media_type != MediaType.VIDEO:
                raise ValueError("SELECTED Best Moment requires video")
            if not self.candidates:
                raise ValueError("SELECTED Best Moment requires candidates")
            if (
                self.selected_start_s is None
                or self.selected_end_s is None
                or self.selected_sample_time_s is None
                or self.selected_score is None
            ):
                raise ValueError("SELECTED Best Moment requires selected window")
            if self.selected_end_s <= self.selected_start_s:
                raise ValueError("selected window must have positive duration")
            starts = [candidate.window_start_s for candidate in self.candidates]
            if self.selected_start_s not in starts:
                raise ValueError("selected start must correspond to one candidate")
        else:
            if self.candidates:
                raise ValueError("non-selected scene cannot contain candidates")
            if any(
                value is not None
                for value in (
                    self.selected_start_s,
                    self.selected_end_s,
                    self.selected_sample_time_s,
                    self.selected_score,
                )
            ):
                raise ValueError("non-selected scene cannot contain selected window")
        return self


class BestMomentStructuralChecks(StrictBestMomentModel):
    source_alignment: bool
    graph_hash_preserved: bool
    quality_hash_preserved: bool
    material_identity_preserved: bool
    placeholders_preserved: bool
    static_images_not_scanned: bool


class BestMomentPlan(StrictBestMomentModel):
    version: str = BEST_MOMENT_VERSION
    subject: str

    source_plan_context_hash: str
    source_video_base_version: str
    source_story_graph_version: str
    source_story_graph_hash: str
    source_shot_quality_version: str
    source_shot_quality_hash: str

    deterministic: bool = True
    candidate_policy: str = "EQUALLY_SPACED_WINDOW_CENTERS_V01"
    scoring_profile: str = "TEMPORAL_TECHNICAL_V01"
    max_candidates: int = Field(ge=3, le=21)

    uses_llm: bool = False
    gpu_required: bool = False
    renders_video: bool = False
    searches_material: bool = False
    changes_material_identity: bool = False
    tracking_triggered: bool = False
    smartfocal_triggered: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    selected_count: int = Field(ge=0)
    placeholder_count: int = Field(ge=0)
    static_image_count: int = Field(ge=0)
    analysis_failed_count: int = Field(ge=0)
    ffmpeg_frames_analyzed: int = Field(ge=0)

    scenes: list[BestMomentSceneResult]
    structural_checks: BestMomentStructuralChecks
    best_moment_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count must equal scenes length")

        selected = sum(
            scene.status == BestMomentStatus.SELECTED
            for scene in self.scenes
        )
        placeholders = sum(
            scene.status == BestMomentStatus.PLACEHOLDER_NOT_APPLICABLE
            for scene in self.scenes
        )
        static_images = sum(
            scene.status == BestMomentStatus.STATIC_IMAGE
            for scene in self.scenes
        )
        failed = sum(
            scene.status == BestMomentStatus.ANALYSIS_FAILED
            for scene in self.scenes
        )

        if self.selected_count != selected:
            raise ValueError("selected_count mismatch")
        if self.placeholder_count != placeholders:
            raise ValueError("placeholder_count mismatch")
        if self.static_image_count != static_images:
            raise ValueError("static_image_count mismatch")
        if self.analysis_failed_count != failed:
            raise ValueError("analysis_failed_count mismatch")
        if selected + placeholders + static_images + failed != self.scene_count:
            raise ValueError("Best Moment statuses do not cover all scenes")

        actual_frames = sum(len(scene.candidates) for scene in self.scenes)
        if self.ffmpeg_frames_analyzed != actual_frames:
            raise ValueError("ffmpeg_frames_analyzed must equal candidate count")

        checks = self.structural_checks
        if not all(
            (
                checks.source_alignment,
                checks.graph_hash_preserved,
                checks.quality_hash_preserved,
                checks.material_identity_preserved,
                checks.placeholders_preserved,
                checks.static_images_not_scanned,
            )
        ):
            raise ValueError("all F10 structural checks must pass")

        if (
            self.uses_llm
            or self.gpu_required
            or self.renders_video
            or self.searches_material
            or self.changes_material_identity
            or self.tracking_triggered
            or self.smartfocal_triggered
            or self.auto_publication
        ):
            raise ValueError("F10 V0.1 guardrail violation")

        return self
