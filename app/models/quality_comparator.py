from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.media_mining import MediaMiningPlan
from app.models.selective_upscaling import SelectiveUpscalingPlan
from app.models.shot_quality import ShotQualityPlan


QUALITY_COMPARATOR_VERSION = "quality-comparator-v0.1"


class StrictQualityComparatorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class QualityComparisonStatus(str, Enum):
    PLACEHOLDER_NOT_COMPARABLE = "PLACEHOLDER_NOT_COMPARABLE"
    BASELINE_ACCEPTED = "BASELINE_ACCEPTED"
    A_B_COMPARISON_REQUIRED = "A_B_COMPARISON_REQUIRED"
    SOURCE_ANALYSIS_FAILED = "SOURCE_ANALYSIS_FAILED"


class QualityComparatorRequest(StrictQualityComparatorModel):
    shot_quality: ShotQualityPlan
    upscaling: SelectiveUpscalingPlan
    media_mining: MediaMiningPlan


class QualityComparisonScene(StrictQualityComparatorModel):
    scene_number: int = Field(ge=1)
    status: QualityComparisonStatus
    baseline_score: float | None = Field(default=None, ge=0.0, le=1.0)
    candidate_name: str | None = None
    comparison_executed: bool = False
    winner: str | None = None
    human_review_required: bool = False
    astronomy_fidelity_required: bool = False
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scene(self):
        if self.comparison_executed:
            raise ValueError("F28 V0.1 does not execute A/B comparisons")
        if self.winner is not None:
            raise ValueError("F28 cannot select winner without A/B evidence")
        if self.status == QualityComparisonStatus.A_B_COMPARISON_REQUIRED:
            if not self.candidate_name:
                raise ValueError("A/B status requires candidate")
            if not self.human_review_required or not self.astronomy_fidelity_required:
                raise ValueError("A/B candidate requires human astronomy review")
        elif self.candidate_name is not None:
            raise ValueError("non-A/B scene cannot contain candidate")
        return self


class QualityComparatorPlan(StrictQualityComparatorModel):
    version: str = QUALITY_COMPARATOR_VERSION
    subject: str
    source_plan_context_hash: str
    source_quality_hash: str
    source_upscaling_hash: str
    source_media_mining_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    gpu_required: bool = False
    analyzes_new_frames: bool = False
    executes_ab_comparison: bool = False
    selects_winner: bool = False
    modifies_media: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    placeholder_count: int = Field(ge=0)
    baseline_accepted_count: int = Field(ge=0)
    ab_required_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    scenes: list[QualityComparisonScene]

    quality_comparator_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count mismatch")
        counts = {
            QualityComparisonStatus.PLACEHOLDER_NOT_COMPARABLE: self.placeholder_count,
            QualityComparisonStatus.BASELINE_ACCEPTED: self.baseline_accepted_count,
            QualityComparisonStatus.A_B_COMPARISON_REQUIRED: self.ab_required_count,
            QualityComparisonStatus.SOURCE_ANALYSIS_FAILED: self.failed_count,
        }
        for status, expected in counts.items():
            if sum(scene.status == status for scene in self.scenes) != expected:
                raise ValueError(f"{status.value} count mismatch")
        if sum(counts.values()) != self.scene_count:
            raise ValueError("F28 statuses do not cover scenes")
        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.analyzes_new_frames
            or self.executes_ab_comparison
            or self.selects_winner
            or self.modifies_media
            or self.auto_publication
        ):
            raise ValueError("F28 guardrail violation")
        return self
