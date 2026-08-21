from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astronomy_director import AstronomyVideoPlan
from app.models.sound_design import SoundDesignPlan


VOICE_STUDIO_VERSION = "voice-studio-v0.1"


class StrictVoiceStudioModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class VoiceSceneStatus(str, Enum):
    VOICE_SELECTION_REQUIRED = "VOICE_SELECTION_REQUIRED"


class TimestampPolicy(str, Enum):
    TTS_NATIVE_BOUNDARIES_FIRST = "TTS_NATIVE_BOUNDARIES_FIRST"


class VoiceStudioRequest(StrictVoiceStudioModel):
    plan: AstronomyVideoPlan
    sound_design: SoundDesignPlan


class VoiceUtterance(StrictVoiceStudioModel):
    scene_number: int = Field(ge=1)
    duration_seconds: float = Field(gt=0.0)
    narration: str = Field(min_length=1)
    locale: str
    status: VoiceSceneStatus = VoiceSceneStatus.VOICE_SELECTION_REQUIRED

    exact_voice_id: str | None = None
    preferred_gender: str = "Male"
    voice_selection_required: bool = True

    timestamp_policy: TimestampPolicy = TimestampPolicy.TTS_NATIVE_BOUNDARIES_FIRST
    native_timestamps_required: bool = True
    astronomy_terms: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_utterance(self):
        if not self.voice_selection_required:
            raise ValueError("F23 requires explicit voice selection")
        if self.exact_voice_id is not None:
            raise ValueError("F23 V0.1 does not pin an exact voice id")
        if not self.native_timestamps_required:
            raise ValueError("F23 requires native TTS timing metadata first")
        return self


class VoiceStudioPlan(StrictVoiceStudioModel):
    version: str = VOICE_STUDIO_VERSION
    subject: str
    source_plan_context_hash: str
    source_sound_design_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    backend_family: str = "MPT_EXISTING_TTS"
    preferred_candidate: str = "EDGE_TTS_EXISTING_INTEGRATION"
    edge_tts_client_license: str = "LGPL-3.0"
    external_service_review_required: bool = True

    uses_llm: bool = False
    gpu_required: bool = False
    generates_audio: bool = False
    tts_invocations: int = 0
    network_calls: int = 0
    downloads_models: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    voice_selection_required_count: int = Field(ge=0)
    utterances: list[VoiceUtterance]

    voice_studio_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.utterances):
            raise ValueError("scene_count mismatch")
        if self.voice_selection_required_count != sum(
            item.voice_selection_required for item in self.utterances
        ):
            raise ValueError("voice selection count mismatch")
        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.generates_audio
            or self.tts_invocations != 0
            or self.network_calls != 0
            or self.downloads_models
            or self.auto_publication
        ):
            raise ValueError("F23 guardrail violation")
        return self
