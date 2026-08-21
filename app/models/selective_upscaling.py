from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.shot_quality import ShotQualityPlan
from app.models.video_base import VideoBasePlan


SELECTIVE_UPSCALING_VERSION = "selective-upscaling-v0.1"


class StrictUpscalingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class UpscaleSceneStatus(str, Enum):
    PLACEHOLDER_NOT_APPLICABLE = "PLACEHOLDER_NOT_APPLICABLE"
    NOT_REQUIRED = "NOT_REQUIRED"
    A_B_REVIEW_REQUIRED = "A_B_REVIEW_REQUIRED"


class SelectiveUpscalingRequest(StrictUpscalingModel):
    video_base: VideoBasePlan
    shot_quality: ShotQualityPlan


class UpscaleScene(StrictUpscalingModel):
    scene_number: int = Field(ge=1)
    status: UpscaleSceneStatus
    source_width: int = Field(ge=0)
    source_height: int = Field(ge=0)
    target_width: int = Field(gt=0)
    target_height: int = Field(gt=0)

    candidate_engine: str | None = None
    execution_ready: bool = False
    astronomy_fidelity_review_required: bool = False
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scene(self):
        if self.execution_ready:
            raise ValueError("F26 V0.1 never auto-executes upscaling")
        if self.status == UpscaleSceneStatus.A_B_REVIEW_REQUIRED:
            if not self.candidate_engine:
                raise ValueError("A/B review requires candidate engine")
            if not self.astronomy_fidelity_review_required:
                raise ValueError("astronomy candidate requires fidelity review")
        else:
            if self.candidate_engine is not None:
                raise ValueError("non-candidate scene cannot pin an engine")
        return self


class SelectiveUpscalingPlan(StrictUpscalingModel):
    version: str = SELECTIVE_UPSCALING_VERSION
    subject: str
    source_plan_context_hash: str
    source_video_base_version: str
    source_quality_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    candidate_engine: str = "Real-ESRGAN-ncnn-vulkan"
    engine_license: str = "MIT"
    model_weights_license: str = "NO_VERIFICADA"

    uses_llm: bool = False
    gpu_required: bool = False
    runs_upscaler: bool = False
    downloads_models: bool = False
    renders_video: bool = False
    changes_material_identity: bool = False
    invents_astronomy_detail: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    placeholder_count: int = Field(ge=0)
    not_required_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    scenes: list[UpscaleScene]

    selective_upscaling_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count mismatch")
        mapping = {
            UpscaleSceneStatus.PLACEHOLDER_NOT_APPLICABLE: self.placeholder_count,
            UpscaleSceneStatus.NOT_REQUIRED: self.not_required_count,
            UpscaleSceneStatus.A_B_REVIEW_REQUIRED: self.candidate_count,
        }
        for status, expected in mapping.items():
            if sum(scene.status == status for scene in self.scenes) != expected:
                raise ValueError(f"{status.value} count mismatch")
        if sum(mapping.values()) != self.scene_count:
            raise ValueError("F26 statuses do not cover scenes")
        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.runs_upscaler
            or self.downloads_models
            or self.renders_video
            or self.changes_material_identity
            or self.invents_astronomy_detail
            or self.auto_publication
        ):
            raise ValueError("F26 guardrail violation")
        return self
