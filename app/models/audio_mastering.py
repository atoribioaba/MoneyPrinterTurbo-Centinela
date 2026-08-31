from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.sound_design import SoundDesignPlan
from app.models.voice_studio import VoiceStudioPlan


AUDIO_MASTERING_VERSION = "audio-mastering-v0.1"


class StrictAudioMasteringModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AudioMasteringStatus(str, Enum):
    INPUTS_REQUIRED = "INPUTS_REQUIRED"


class AudioMasteringRequest(StrictAudioMasteringModel):
    voice_studio: VoiceStudioPlan
    sound_design: SoundDesignPlan


class AudioMasteringPlan(StrictAudioMasteringModel):
    version: str = AUDIO_MASTERING_VERSION
    subject: str
    source_plan_context_hash: str
    source_voice_studio_hash: str
    source_sound_design_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    status: AudioMasteringStatus = AudioMasteringStatus.INPUTS_REQUIRED
    profile: str = "VOICE_LED_SOCIAL_PROJECT_TARGET"
    normalization_method: str = "FFMPEG_LOUDNORM_TWO_PASS_WHEN_INPUT_AVAILABLE"

    target_i_lufs: float = -16.0
    target_lra_lu: float = 7.0
    target_tp_dbtp: float = -1.0
    platform_guarantee: bool = False

    uses_llm: bool = False
    gpu_required: bool = False
    renders_audio: bool = False
    modifies_audio: bool = False
    ffmpeg_invocations: int = 0
    auto_publication: bool = False

    voice_audio_ready: bool = False
    sound_assets_ready: bool = False
    mastering_ready: bool = False

    audio_mastering_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.mastering_ready:
            raise ValueError("F24 V0.1 must not claim mastering readiness")
        if self.voice_audio_ready or self.sound_assets_ready:
            raise ValueError("F24 V0.1 has no selected/generated audio inputs")
        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.renders_audio
            or self.modifies_audio
            or self.ffmpeg_invocations != 0
            or self.auto_publication
        ):
            raise ValueError("F24 guardrail violation")
        return self
