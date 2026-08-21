from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.audio_mastering import AudioMasteringPlan
from app.models.quality_comparator import QualityComparatorPlan
from app.models.sound_design import SoundDesignPlan
from app.models.subtitle_intelligence import SubtitleIntelligencePlan
from app.models.voice_studio import VoiceStudioPlan


QUALITY_GATES_VERSION = "quality-gates-v0.1"


class StrictQualityGatesModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class QualityGateStatus(str, Enum):
    BLOCKED = "BLOCKED"
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"


class QualityGatesRequest(StrictQualityGatesModel):
    comparator: QualityComparatorPlan
    sound_design: SoundDesignPlan
    voice_studio: VoiceStudioPlan
    audio_mastering: AudioMasteringPlan
    subtitles: SubtitleIntelligencePlan


class QualityGateCheck(StrictQualityGatesModel):
    check_id: str
    passed: bool
    blocking: bool = True
    detail: str


class QualityGatesPlan(StrictQualityGatesModel):
    version: str = QUALITY_GATES_VERSION
    subject: str
    source_plan_context_hash: str
    source_comparator_hash: str
    source_sound_design_hash: str
    source_voice_studio_hash: str
    source_audio_mastering_hash: str
    source_subtitles_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_media: bool = False
    modifies_media: bool = False
    auto_publication: bool = False
    human_approval_required: bool = True

    status: QualityGateStatus
    check_count: int = Field(ge=1)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    technical_ready: bool
    publication_eligible_after_human_approval: bool
    checks: list[QualityGateCheck]

    quality_gates_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.check_count != len(self.checks):
            raise ValueError("check_count mismatch")
        if self.passed_count != sum(check.passed for check in self.checks):
            raise ValueError("passed_count mismatch")
        if self.failed_count != sum(not check.passed for check in self.checks):
            raise ValueError("failed_count mismatch")
        expected_ready = all(check.passed for check in self.checks if check.blocking)
        if self.technical_ready != expected_ready:
            raise ValueError("technical_ready mismatch")
        expected_status = (
            QualityGateStatus.READY_FOR_HUMAN_REVIEW
            if expected_ready
            else QualityGateStatus.BLOCKED
        )
        if self.status != expected_status:
            raise ValueError("status mismatch")
        if self.publication_eligible_after_human_approval != expected_ready:
            raise ValueError("publication eligibility mismatch")
        if not self.human_approval_required:
            raise ValueError("human approval is mandatory")
        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.renders_media
            or self.modifies_media
            or self.auto_publication
        ):
            raise ValueError("F29 guardrail violation")
        return self
