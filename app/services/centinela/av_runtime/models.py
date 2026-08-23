from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


R7_AV_RUNTIME_VERSION = "av-runtime-v0.1"


class StrictAVModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AudioSceneTiming(StrictAVModel):
    scene_number: int = Field(ge=1)
    start_s: float = Field(ge=0.0)
    end_s: float = Field(gt=0.0)
    duration_s: float = Field(gt=0.0)
    token_start: int = Field(ge=0)
    token_end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_timing(self):
        if self.end_s <= self.start_s:
            raise ValueError("scene timing end must be after start")
        if abs((self.end_s - self.start_s) - self.duration_s) > 0.02:
            raise ValueError("scene duration does not match boundaries")
        if self.token_end < self.token_start:
            raise ValueError("scene token range is invalid")
        return self


class SubtitleCue(StrictAVModel):
    index: int = Field(ge=1)
    scene_number: int = Field(ge=1)
    start_s: float = Field(ge=0.0)
    end_s: float = Field(gt=0.0)
    text: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_timing(self):
        if self.end_s <= self.start_s:
            raise ValueError("subtitle cue end must be after start")
        return self


class AudioBundle(StrictAVModel):
    version: Literal["av-runtime-v0.1"] = R7_AV_RUNTIME_VERSION
    subject: str
    source_plan_context_hash: str
    source_final_script_hash: str
    source_material_selector_version: str

    tts_backend: Literal["QWEN3_TTS_LOCAL"] = "QWEN3_TTS_LOCAL"
    tts_voice_id: str = "qwen3tts:centinela-cinematico"
    qwen_runtime_python: str
    qwen_adapter: str
    qwen_model_path: str
    qwen_native_timestamps: bool = False

    timestamp_method: Literal[
        "FASTER_WHISPER_SCRIPT_ALIGNED"
    ] = "FASTER_WHISPER_SCRIPT_ALIGNED"
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    alignment_ratio: float = Field(ge=0.0, le=1.0)

    pronunciation_applied: list[str] = Field(default_factory=list)
    pronunciation_deferred: list[str] = Field(default_factory=list)

    voice_raw_artifact_id: str
    voice_master_artifact_id: str
    subtitle_artifact_id: str

    voice_raw_sha256: str = Field(min_length=64, max_length=64)
    voice_master_sha256: str = Field(min_length=64, max_length=64)
    subtitle_sha256: str = Field(min_length=64, max_length=64)

    duration_seconds: float = Field(gt=0.0)
    sample_rate_hz: int = 48000
    channels: int = Field(ge=1, le=8)

    target_i_lufs: float = -16.0
    target_lra_lu: float = 7.0
    target_tp_dbtp: float = -1.0
    verified_i_lufs: float
    verified_tp_dbtp: float

    scene_count: int = Field(ge=1)
    scenes: list[AudioSceneTiming]
    subtitle_cue_count: int = Field(ge=1)
    subtitles: list[SubtitleCue]

    music_included: bool = False
    sound_assets_count: int = 0
    sound_policy: str = (
        "VOICE_ONLY_UNTIL_A_VERIFIED_LICENSED_SOUND_ASSET_IS_SELECTED"
    )
    external_network_used: bool = False
    model_downloads: bool = False
    auto_publication: bool = False
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_bundle(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("audio scene_count mismatch")
        if self.subtitle_cue_count != len(self.subtitles):
            raise ValueError("subtitle cue_count mismatch")
        if self.qwen_native_timestamps:
            raise ValueError("Qwen V0.1 integration does not expose native timestamps")
        if (
            self.music_included
            or self.sound_assets_count != 0
            or self.external_network_used
            or self.model_downloads
            or self.auto_publication
        ):
            raise ValueError("R7 audio guardrail violation")
        return self


class VideoBaseManifest(StrictAVModel):
    version: Literal["av-runtime-v0.1"] = R7_AV_RUNTIME_VERSION
    subject: str
    source_plan_context_hash: str
    source_audio_bundle_artifact_id: str
    source_material_selection_artifact_id: str
    source_media_resolution_artifact_id: str

    social_video_artifact_id: str
    master_video_artifact_id: str
    review_preview_artifact_id: str
    subtitle_artifact_id: str

    social_width: int = 1080
    social_height: int = 1920
    master_width: int = 2160
    master_height: int = 3840
    fps: int = 30

    social_codec: str
    master_codec: str
    social_codec_fallback: bool
    master_codec_fallback: bool

    social_duration_seconds: float = Field(gt=0.0)
    master_duration_seconds: float = Field(gt=0.0)
    review_preview_duration_seconds: float = Field(gt=0.0)

    social_sha256: str = Field(min_length=64, max_length=64)
    master_sha256: str = Field(min_length=64, max_length=64)
    review_preview_sha256: str = Field(min_length=64, max_length=64)

    clean_base_audio_streams: int = 0
    review_preview_audio_streams: int = 1
    master_direct_from_selected_sources: bool = True
    master_derived_from_social: bool = False
    subtitle_burned_in: bool = False
    color_policy: str = "SOURCE_PRESERVING_NO_SYNTHETIC_GRADE_V0.1"

    smartfocal_scene_count: int = Field(ge=0)
    fit_scene_count: int = Field(ge=0)
    cover_scene_count: int = Field(ge=0)
    scene_count: int = Field(ge=1)

    social_render_manifest: dict[str, Any]
    master_render_manifest: dict[str, Any]

    auto_publication: bool = False
    wangp_triggered: bool = False
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_manifest(self):
        if self.master_derived_from_social:
            raise ValueError("master must never be derived from the social encode")
        if not self.master_direct_from_selected_sources:
            raise ValueError("master must render directly from selected source media")
        if self.clean_base_audio_streams != 0:
            raise ValueError("clean video bases must not contain audio")
        if self.review_preview_audio_streams != 1:
            raise ValueError("review preview must contain exactly one audio stream")
        if self.auto_publication or self.wangp_triggered:
            raise ValueError("R7 video guardrail violation")
        if self.fit_scene_count + self.cover_scene_count != self.scene_count:
            raise ValueError("fit/cover counts do not cover all scenes")
        return self
