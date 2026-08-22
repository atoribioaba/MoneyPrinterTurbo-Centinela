from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.production_orchestrator import ProductionOrchestratorPlan
from app.models.video_base import VideoBaseRenderManifest

VIDEO_BASE_E2E_VERSION = "video-base-e2e-v0.1"


class StrictVideoBaseE2EModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class VideoBaseE2EStatus(str, Enum):
    WAITING_FOR_ORCHESTRATOR = "WAITING_FOR_ORCHESTRATOR"
    WAITING_FOR_REAL_VIDEO_BASE = "WAITING_FOR_REAL_VIDEO_BASE"
    WAITING_FOR_CLEAN_VIDEO_BASE = "WAITING_FOR_CLEAN_VIDEO_BASE"
    VIDEO_BASE_E2E_PASS = "VIDEO_BASE_E2E_PASS"
    VIDEO_BASE_E2E_FAIL = "VIDEO_BASE_E2E_FAIL"


class VideoArtifactProbe(StrictVideoBaseE2EModel):
    file_path: str
    exists: bool
    sha256: str | None = None
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)
    fps: float = Field(default=0.0, ge=0.0)
    video_codec: str | None = None
    pixel_format: str | None = None
    audio_stream_count: int = Field(default=0, ge=0)


class VideoBaseE2ERequest(StrictVideoBaseE2EModel):
    orchestrator: ProductionOrchestratorPlan
    manifest: VideoBaseRenderManifest | None = None
    probe: VideoArtifactProbe | None = None

    @model_validator(mode="after")
    def validate_pair(self):
        if (self.manifest is None) != (self.probe is None):
            raise ValueError("manifest and probe must be supplied together")
        return self


class VideoBaseE2ECheck(StrictVideoBaseE2EModel):
    check_id: str
    passed: bool
    detail: str


class VideoBaseE2EPlan(StrictVideoBaseE2EModel):
    version: str = VIDEO_BASE_E2E_VERSION
    source_production_orchestrator_hash: str
    deterministic: bool = True
    verification_only: bool = True
    resource_class: str = "LIGHT"
    renders_video: bool = False
    modifies_media: bool = False
    network_calls: int = 0
    uses_llm: bool = False
    auto_publication: bool = False

    status: VideoBaseE2EStatus
    clean_base_required: bool = True
    real_artifact_present: bool
    check_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    checks: list[VideoBaseE2ECheck]
    video_base_e2e_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.check_count != len(self.checks): raise ValueError("check_count mismatch")
        if self.passed_count != sum(x.passed for x in self.checks): raise ValueError("passed_count mismatch")
        if self.failed_count != sum(not x.passed for x in self.checks): raise ValueError("failed_count mismatch")
        if not self.verification_only or self.renders_video or self.modifies_media or self.network_calls or self.uses_llm or self.auto_publication:
            raise ValueError("F52 guardrail violation")
        return self
