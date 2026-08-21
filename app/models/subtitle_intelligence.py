from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.voice_studio import VoiceStudioPlan


SUBTITLE_INTELLIGENCE_VERSION = "subtitle-intelligence-v0.1"


class StrictSubtitleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SubtitleSceneStatus(str, Enum):
    WAITING_NATIVE_TTS_TIMESTAMPS = "WAITING_NATIVE_TTS_TIMESTAMPS"
    NATIVE_TIMING_READY = "NATIVE_TIMING_READY"


class NativeTimingCue(StrictSubtitleModel):
    scene_number: int = Field(ge=1)
    start_s: float = Field(ge=0.0)
    end_s: float = Field(gt=0.0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_timing(self):
        if self.end_s <= self.start_s:
            raise ValueError("subtitle cue end must be after start")
        return self


class SubtitleIntelligenceRequest(StrictSubtitleModel):
    voice_studio: VoiceStudioPlan
    native_timing_cues: list[NativeTimingCue] = Field(default_factory=list)


class SubtitleScene(StrictSubtitleModel):
    scene_number: int = Field(ge=1)
    status: SubtitleSceneStatus
    cue_count: int = Field(ge=0)
    cues: list[NativeTimingCue] = Field(default_factory=list)
    whisper_fallback_required: bool = False

    @model_validator(mode="after")
    def validate_scene(self):
        if self.cue_count != len(self.cues):
            raise ValueError("cue_count mismatch")
        if self.status == SubtitleSceneStatus.WAITING_NATIVE_TTS_TIMESTAMPS:
            if self.cues:
                raise ValueError("waiting scene cannot contain cues")
        else:
            if not self.cues:
                raise ValueError("native-ready scene requires cues")
        return self


class SubtitleIntelligencePlan(StrictSubtitleModel):
    version: str = SUBTITLE_INTELLIGENCE_VERSION
    subject: str
    source_plan_context_hash: str
    source_voice_studio_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    timestamp_priority: str = "NATIVE_TTS_BOUNDARIES_FIRST"
    fallback_candidate: str = "faster-whisper"
    fallback_candidate_license: str = "MIT"

    uses_llm: bool = False
    gpu_required: bool = False
    whisper_triggered: bool = False
    downloads_models: bool = False
    transcribes_audio: bool = False
    auto_publication: bool = False

    max_lines: int = 2
    max_chars_per_line_project_target: int = 32

    scene_count: int = Field(ge=1)
    native_ready_count: int = Field(ge=0)
    waiting_count: int = Field(ge=0)
    cue_count: int = Field(ge=0)
    scenes: list[SubtitleScene]

    subtitle_intelligence_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count mismatch")
        if self.native_ready_count != sum(
            scene.status == SubtitleSceneStatus.NATIVE_TIMING_READY
            for scene in self.scenes
        ):
            raise ValueError("native_ready_count mismatch")
        if self.waiting_count != sum(
            scene.status == SubtitleSceneStatus.WAITING_NATIVE_TTS_TIMESTAMPS
            for scene in self.scenes
        ):
            raise ValueError("waiting_count mismatch")
        if self.cue_count != sum(scene.cue_count for scene in self.scenes):
            raise ValueError("cue_count mismatch")
        if self.native_ready_count + self.waiting_count != self.scene_count:
            raise ValueError("subtitle statuses do not cover scenes")
        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.whisper_triggered
            or self.downloads_models
            or self.transcribes_audio
            or self.auto_publication
        ):
            raise ValueError("F25 guardrail violation")
        return self
