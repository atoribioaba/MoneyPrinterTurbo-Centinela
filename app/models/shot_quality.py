from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astromedia import MediaType
from app.models.video_base import VideoBasePlan
from app.models.visual_story_graph import VisualStoryGraph


SHOT_QUALITY_VERSION = "shot-quality-v0.1"


class StrictShotQualityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ShotQualityStatus(str, Enum):
    SCORED = "SCORED"
    NOT_SCORABLE = "NOT_SCORABLE"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"


class ShotQualityBand(str, Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    USABLE = "USABLE"
    WEAK = "WEAK"
    NOT_SCORABLE = "NOT_SCORABLE"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"


class ShotQualityRequest(StrictShotQualityModel):
    video_base: VideoBasePlan
    story_graph: VisualStoryGraph


class RepresentativeFrameMetrics(StrictShotQualityModel):
    sample_time_s: float = Field(ge=0.0)
    blur_metric: float = Field(ge=0.0)
    y_min: float = Field(ge=0.0, le=255.0)
    y_max: float = Field(ge=0.0, le=255.0)
    y_avg: float = Field(ge=0.0, le=255.0)
    sat_avg: float = Field(ge=0.0)
    luma_span: float = Field(ge=0.0, le=255.0)
    ffmpeg_binary: str


class ShotQualityComponents(StrictShotQualityModel):
    resolution_adequacy: float = Field(ge=0.0, le=1.0)
    framing_efficiency: float = Field(ge=0.0, le=1.0)
    sharpness_relative: float = Field(ge=0.0, le=1.0)
    luma_range: float = Field(ge=0.0, le=1.0)


class ShotQualitySceneScore(StrictShotQualityModel):
    scene_number: int = Field(ge=1)
    node_id: str
    selected_media_id: str | None = None
    media_type: MediaType | None = None
    source_path: str | None = None

    placeholder: bool
    status: ShotQualityStatus
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    band: ShotQualityBand

    components: ShotQualityComponents | None = None
    frame_metrics: RepresentativeFrameMetrics | None = None

    flags: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scene_score(self):
        if self.status == ShotQualityStatus.SCORED:
            if self.placeholder:
                raise ValueError("placeholder scene cannot be SCORED")
            if self.score is None or self.components is None or self.frame_metrics is None:
                raise ValueError("SCORED scene requires score, components and frame metrics")
            if self.band in {
                ShotQualityBand.NOT_SCORABLE,
                ShotQualityBand.ANALYSIS_FAILED,
            }:
                raise ValueError("SCORED scene has invalid band")
        else:
            if self.score is not None or self.components is not None:
                raise ValueError("non-SCORED scene cannot contain quality score/components")
            if self.status == ShotQualityStatus.NOT_SCORABLE:
                if not self.placeholder:
                    raise ValueError("NOT_SCORABLE is reserved for placeholder scenes in F9 V0.1")
                if self.band != ShotQualityBand.NOT_SCORABLE:
                    raise ValueError("NOT_SCORABLE status/band mismatch")
            if self.status == ShotQualityStatus.ANALYSIS_FAILED:
                if self.placeholder:
                    raise ValueError("placeholder cannot be ANALYSIS_FAILED")
                if self.band != ShotQualityBand.ANALYSIS_FAILED:
                    raise ValueError("ANALYSIS_FAILED status/band mismatch")
        return self


class ShotQualityStructuralChecks(StrictShotQualityModel):
    source_alignment: bool
    graph_hash_preserved: bool
    placeholders_preserved: bool
    no_best_moment_search: bool
    no_material_search: bool


class ShotQualityPlan(StrictShotQualityModel):
    version: str = SHOT_QUALITY_VERSION
    subject: str

    source_plan_context_hash: str
    source_video_base_version: str
    source_story_graph_version: str
    source_story_graph_hash: str

    deterministic: bool = True
    representative_frame_policy: str = "F6_SOURCE_START_SINGLE_FRAME"
    heuristic_profile: str = "TECHNICAL_V01"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_video: bool = False
    searches_material: bool = False
    best_moment_search_triggered: bool = False
    tracking_triggered: bool = False
    smartfocal_triggered: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    scored_count: int = Field(ge=0)
    not_scorable_count: int = Field(ge=0)
    analysis_failed_count: int = Field(ge=0)
    ffmpeg_frames_analyzed: int = Field(ge=0)

    mean_score: float | None = Field(default=None, ge=0.0, le=1.0)

    scenes: list[ShotQualitySceneScore]
    structural_checks: ShotQualityStructuralChecks
    quality_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count must equal scenes length")

        scored = sum(
            scene.status == ShotQualityStatus.SCORED for scene in self.scenes
        )
        not_scorable = sum(
            scene.status == ShotQualityStatus.NOT_SCORABLE for scene in self.scenes
        )
        failed = sum(
            scene.status == ShotQualityStatus.ANALYSIS_FAILED for scene in self.scenes
        )

        if self.scored_count != scored:
            raise ValueError("scored_count mismatch")
        if self.not_scorable_count != not_scorable:
            raise ValueError("not_scorable_count mismatch")
        if self.analysis_failed_count != failed:
            raise ValueError("analysis_failed_count mismatch")
        if scored + not_scorable + failed != self.scene_count:
            raise ValueError("scene quality status counts do not cover all scenes")
        if self.ffmpeg_frames_analyzed != scored:
            raise ValueError("F9 V0.1 analyzes exactly one frame per successfully scored scene")

        scores = [scene.score for scene in self.scenes if scene.score is not None]
        if scores:
            expected_mean = round(sum(scores) / len(scores), 3)
            if self.mean_score != expected_mean:
                raise ValueError("mean_score mismatch")
        elif self.mean_score is not None:
            raise ValueError("mean_score must be null when no scenes are scored")

        checks = self.structural_checks
        if not all(
            (
                checks.source_alignment,
                checks.graph_hash_preserved,
                checks.placeholders_preserved,
                checks.no_best_moment_search,
                checks.no_material_search,
            )
        ):
            raise ValueError("all F9 structural checks must pass")

        if (
            self.uses_llm
            or self.gpu_required
            or self.renders_video
            or self.searches_material
            or self.best_moment_search_triggered
            or self.tracking_triggered
            or self.smartfocal_triggered
            or self.auto_publication
        ):
            raise ValueError("F9 V0.1 guardrail violation")

        return self
