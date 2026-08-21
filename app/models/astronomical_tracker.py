from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astromedia import MediaType
from app.models.best_moment import BestMomentPlan
from app.models.shot_quality import ShotQualityPlan
from app.models.video_base import VideoBasePlan
from app.models.visual_story_graph import VisualStoryGraph


ASTRONOMICAL_TRACKER_VERSION = "astronomical-object-tracker-v0.1"


class StrictTrackerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class TrackingSeedSource(str, Enum):
    MANUAL = "MANUAL"
    EXTERNAL_GROUNDING = "EXTERNAL_GROUNDING"


class TrackingSceneStatus(str, Enum):
    TRACKED = "TRACKED"
    TRACKED_PARTIAL = "TRACKED_PARTIAL"
    PLACEHOLDER_NOT_APPLICABLE = "PLACEHOLDER_NOT_APPLICABLE"
    STATIC_IMAGE_NOT_APPLICABLE = "STATIC_IMAGE_NOT_APPLICABLE"
    BEST_MOMENT_UNAVAILABLE = "BEST_MOMENT_UNAVAILABLE"
    SEED_REQUIRED = "SEED_REQUIRED"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    TRACKING_FAILED = "TRACKING_FAILED"


class NormalizedBoundingBox(StrictTrackerModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_edges(self):
        if self.x + self.width > 1.000001:
            raise ValueError("normalized bbox exceeds right image edge")
        if self.y + self.height > 1.000001:
            raise ValueError("normalized bbox exceeds bottom image edge")
        return self


class TrackingSeed(StrictTrackerModel):
    scene_number: int = Field(ge=1)
    subject_label: str = Field(min_length=1, max_length=200)
    bbox: NormalizedBoundingBox
    source: TrackingSeedSource = TrackingSeedSource.MANUAL


class TrackingPoint(StrictTrackerModel):
    timestamp_s: float = Field(ge=0.0)
    bbox: NormalizedBoundingBox
    center_x: float = Field(ge=0.0, le=1.0)
    center_y: float = Field(ge=0.0, le=1.0)
    tracking_ok: bool = True


class AstronomicalTrackingRequest(StrictTrackerModel):
    video_base: VideoBasePlan
    story_graph: VisualStoryGraph
    shot_quality: ShotQualityPlan
    best_moment: BestMomentPlan
    seeds: list[TrackingSeed] = Field(default_factory=list)
    backend: str = "opencv_csrt"
    sample_rate_hz: float = Field(default=2.0, gt=0.0, le=10.0)

    @model_validator(mode="after")
    def validate_seeds(self):
        numbers = [seed.scene_number for seed in self.seeds]
        if len(numbers) != len(set(numbers)):
            raise ValueError("only one tracking seed is allowed per scene")
        return self


class TrackingSceneResult(StrictTrackerModel):
    scene_number: int = Field(ge=1)
    node_id: str

    selected_media_id: str | None = None
    media_type: MediaType | None = None
    source_path: str | None = None

    status: TrackingSceneStatus

    subject_label: str | None = None
    seed_source: TrackingSeedSource | None = None
    seed_bbox: NormalizedBoundingBox | None = None

    window_start_s: float | None = Field(default=None, ge=0.0)
    window_end_s: float | None = Field(default=None, gt=0.0)

    backend: str | None = None
    complete_track: bool | None = None

    points: list[TrackingPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self):
        if self.status in {
            TrackingSceneStatus.TRACKED,
            TrackingSceneStatus.TRACKED_PARTIAL,
        }:
            if self.media_type != MediaType.VIDEO:
                raise ValueError("tracked scene must be VIDEO")
            if not self.subject_label or self.seed_bbox is None:
                raise ValueError("tracked scene requires subject and seed")
            if self.window_start_s is None or self.window_end_s is None:
                raise ValueError("tracked scene requires Best Moment window")
            if self.window_end_s <= self.window_start_s:
                raise ValueError("tracking window must have positive duration")
            if not self.points:
                raise ValueError("tracked scene requires tracking points")
            if self.complete_track is None:
                raise ValueError("tracked scene requires complete_track flag")
            if self.status == TrackingSceneStatus.TRACKED and not self.complete_track:
                raise ValueError("TRACKED requires complete_track=True")
            if (
                self.status == TrackingSceneStatus.TRACKED_PARTIAL
                and self.complete_track
            ):
                raise ValueError("TRACKED_PARTIAL requires complete_track=False")
        else:
            if self.points:
                raise ValueError("non-tracked scene cannot contain points")
        return self


class TrackingStructuralChecks(StrictTrackerModel):
    source_alignment: bool
    graph_hash_preserved: bool
    quality_hash_preserved: bool
    best_moment_hash_preserved: bool
    material_identity_preserved: bool
    best_moment_window_preserved: bool
    no_reframing: bool


class AstronomicalTrackingPlan(StrictTrackerModel):
    version: str = ASTRONOMICAL_TRACKER_VERSION
    subject: str

    source_plan_context_hash: str
    source_video_base_version: str
    source_story_graph_version: str
    source_story_graph_hash: str
    source_shot_quality_version: str
    source_shot_quality_hash: str
    source_best_moment_version: str
    source_best_moment_hash: str

    deterministic: bool = True
    tracking_phase: bool = True
    backend_policy: str = "EXPLICIT_SEED_SINGLE_OBJECT_TRACKING_V01"
    resource_class: str = "MEDIUM"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_video: bool = False
    searches_material: bool = False
    changes_material_identity: bool = False
    best_moment_search_triggered: bool = False
    smartfocal_triggered: bool = False
    reframing_triggered: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    tracked_count: int = Field(ge=0)
    partial_count: int = Field(ge=0)
    placeholder_count: int = Field(ge=0)
    static_image_count: int = Field(ge=0)
    seed_required_count: int = Field(ge=0)
    backend_unavailable_count: int = Field(ge=0)
    tracking_failed_count: int = Field(ge=0)
    backend_invocations: int = Field(ge=0)
    tracking_point_count: int = Field(ge=0)

    scenes: list[TrackingSceneResult]
    structural_checks: TrackingStructuralChecks
    tracking_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count must equal scenes length")

        counts = {
            TrackingSceneStatus.TRACKED: 0,
            TrackingSceneStatus.TRACKED_PARTIAL: 0,
            TrackingSceneStatus.PLACEHOLDER_NOT_APPLICABLE: 0,
            TrackingSceneStatus.STATIC_IMAGE_NOT_APPLICABLE: 0,
            TrackingSceneStatus.SEED_REQUIRED: 0,
            TrackingSceneStatus.BACKEND_UNAVAILABLE: 0,
            TrackingSceneStatus.TRACKING_FAILED: 0,
            TrackingSceneStatus.BEST_MOMENT_UNAVAILABLE: 0,
        }
        for scene in self.scenes:
            counts[scene.status] += 1

        if self.tracked_count != counts[TrackingSceneStatus.TRACKED]:
            raise ValueError("tracked_count mismatch")
        if self.partial_count != counts[TrackingSceneStatus.TRACKED_PARTIAL]:
            raise ValueError("partial_count mismatch")
        if (
            self.placeholder_count
            != counts[TrackingSceneStatus.PLACEHOLDER_NOT_APPLICABLE]
        ):
            raise ValueError("placeholder_count mismatch")
        if (
            self.static_image_count
            != counts[TrackingSceneStatus.STATIC_IMAGE_NOT_APPLICABLE]
        ):
            raise ValueError("static_image_count mismatch")
        if self.seed_required_count != counts[TrackingSceneStatus.SEED_REQUIRED]:
            raise ValueError("seed_required_count mismatch")
        if (
            self.backend_unavailable_count
            != counts[TrackingSceneStatus.BACKEND_UNAVAILABLE]
        ):
            raise ValueError("backend_unavailable_count mismatch")
        expected_failed = (
            counts[TrackingSceneStatus.TRACKING_FAILED]
            + counts[TrackingSceneStatus.BEST_MOMENT_UNAVAILABLE]
        )
        if self.tracking_failed_count != expected_failed:
            raise ValueError("tracking_failed_count mismatch")

        actual_points = sum(len(scene.points) for scene in self.scenes)
        if self.tracking_point_count != actual_points:
            raise ValueError("tracking_point_count mismatch")

        tracked_like = self.tracked_count + self.partial_count
        if self.backend_invocations < tracked_like:
            raise ValueError("backend_invocations cannot be below tracked scenes")

        checks = self.structural_checks
        if not all(
            (
                checks.source_alignment,
                checks.graph_hash_preserved,
                checks.quality_hash_preserved,
                checks.best_moment_hash_preserved,
                checks.material_identity_preserved,
                checks.best_moment_window_preserved,
                checks.no_reframing,
            )
        ):
            raise ValueError("all F11 structural checks must pass")

        if (
            self.uses_llm
            or self.gpu_required
            or self.renders_video
            or self.searches_material
            or self.changes_material_identity
            or self.best_moment_search_triggered
            or self.smartfocal_triggered
            or self.reframing_triggered
            or self.auto_publication
        ):
            raise ValueError("F11 V0.1 guardrail violation")

        return self
