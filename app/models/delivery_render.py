from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.quality_gates import QualityGatesPlan


DELIVERY_RENDER_VERSION = "delivery-render-v0.1"


class StrictDeliveryRenderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DeliveryRenderStatus(str, Enum):
    BLOCKED_BY_QUALITY_GATES = "BLOCKED_BY_QUALITY_GATES"
    READY_FOR_EXPLICIT_RENDER_APPROVAL = "READY_FOR_EXPLICIT_RENDER_APPROVAL"


class FFmpegCapabilityHint(StrictDeliveryRenderModel):
    ffmpeg_present: bool
    ffmpeg_version: str | None = None
    h264_nvenc_listed: bool = False
    libx264_listed: bool = False
    nvenc_social_probe_success: bool | None = None
    nvenc_master_probe_success: bool | None = None
    capability_probe_invocations: int = Field(default=0, ge=0)


class DeliveryRenderRequest(StrictDeliveryRenderModel):
    quality_gates: QualityGatesPlan
    ffmpeg: FFmpegCapabilityHint


class DeliveryProfile(StrictDeliveryRenderModel):
    profile_id: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: int = Field(gt=0)
    source_strategy: str = "ORIGINAL_SOURCE_RERENDER"
    requested_codec: str
    fallback_codec: str = "libx264"
    effective_codec_candidate: str
    pixel_format: str = "yuv420p"
    execution_ready: bool = False

    @model_validator(mode="after")
    def validate_profile(self):
        if self.source_strategy != "ORIGINAL_SOURCE_RERENDER":
            raise ValueError("F30 must re-render from original sources")
        if self.execution_ready:
            raise ValueError("F30 V0.1 does not execute project render")
        return self


class DeliveryRenderPlan(StrictDeliveryRenderModel):
    version: str = DELIVERY_RENDER_VERSION
    subject: str
    source_plan_context_hash: str
    source_quality_gates_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "MEDIUM_CAPABILITY_PROBE"

    status: DeliveryRenderStatus

    ffmpeg_present: bool
    ffmpeg_version: str | None = None
    h264_nvenc_listed: bool
    libx264_listed: bool
    nvenc_social_probe_success: bool | None = None
    nvenc_master_probe_success: bool | None = None
    capability_probe_invocations: int = Field(ge=0)

    uses_llm: bool = False
    project_render_invocations: int = 0
    renders_project_video: bool = False
    upscales_social_to_master: bool = False
    downloads_dependencies: bool = False
    auto_publication: bool = False
    human_render_approval_required: bool = True

    profile_count: int = Field(ge=1)
    profiles: list[DeliveryProfile]

    delivery_render_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.profile_count != len(self.profiles):
            raise ValueError("profile_count mismatch")
        if self.status not in {
            DeliveryRenderStatus.BLOCKED_BY_QUALITY_GATES,
            DeliveryRenderStatus.READY_FOR_EXPLICIT_RENDER_APPROVAL,
        }:
            raise ValueError("invalid delivery status")
        if self.upscales_social_to_master:
            raise ValueError("F30 must not upscale social output into master")
        if (
            not self.planning_only
            or self.uses_llm
            or self.project_render_invocations != 0
            or self.renders_project_video
            or self.downloads_dependencies
            or self.auto_publication
            or not self.human_render_approval_required
        ):
            raise ValueError("F30 guardrail violation")
        return self
