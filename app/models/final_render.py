from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.finalization_e2e import (
    FinalVideoArtifactProbe,
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)

FINAL_RENDER_VERSION = "final-render-v0.1"
MASTER_PROFILE_ID = "MASTER_VERTICAL_2160X3840"
SOCIAL_PROFILE_ID = "SOCIAL_VERTICAL_1080X1920"


class StrictFinalRenderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class FinalRenderArtifact(StrictFinalRenderModel):
    profile_id: Literal[
        "MASTER_VERTICAL_2160X3840",
        "SOCIAL_VERTICAL_1080X1920",
    ]
    artifact_id: str = Field(min_length=1, max_length=128)
    file_path: str = Field(min_length=1, max_length=4096)
    sha256: str = Field(min_length=64, max_length=64)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0.0)
    codec: str = Field(min_length=1, max_length=64)
    pixel_format: str | None = Field(default=None, max_length=64)
    duration_seconds: float = Field(gt=0.0)
    audio_stream_count: int = Field(ge=1)
    subtitles_ready: bool = True
    publication_rights_ready: bool = True
    source_video_base_artifact_id: str = Field(min_length=1, max_length=128)
    source_video_base_sha256: str = Field(min_length=64, max_length=64)
    source_audio_artifact_id: str = Field(min_length=1, max_length=128)
    source_subtitle_artifact_id: str = Field(min_length=1, max_length=128)
    video_processing: Literal["STREAM_COPY"] = "STREAM_COPY"
    audio_codec: str = Field(min_length=1, max_length=64)
    subtitle_mode: Literal["SIDECAR_PRESERVED"] = "SIDECAR_PRESERVED"
    ffprobe: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_profile(self):
        expected = {
            MASTER_PROFILE_ID: (2160, 3840),
            SOCIAL_PROFILE_ID: (1080, 1920),
        }[self.profile_id]
        if (self.width, self.height) != expected:
            raise ValueError(f"{self.profile_id} resolution mismatch")
        if abs(self.fps - 30.0) > 0.05:
            raise ValueError(f"{self.profile_id} requires 30 fps")
        if self.audio_stream_count < 1:
            raise ValueError(f"{self.profile_id} requires audio")
        if not self.subtitles_ready:
            raise ValueError(f"{self.profile_id} requires approved subtitles")
        if not self.publication_rights_ready:
            raise ValueError(f"{self.profile_id} requires publication rights")
        try:
            int(self.sha256, 16)
            int(self.source_video_base_sha256, 16)
        except ValueError as exc:
            raise ValueError("render SHA256 fields must be hexadecimal") from exc
        return self

    def to_finalization_probe(self) -> FinalVideoArtifactProbe:
        return FinalVideoArtifactProbe(
            profile_id=self.profile_id,
            file_path=self.file_path,
            exists=True,
            sha256=self.sha256,
            width=self.width,
            height=self.height,
            fps=self.fps,
            codec=self.codec,
            audio_stream_count=self.audio_stream_count,
            subtitles_ready=self.subtitles_ready,
            publication_rights_ready=self.publication_rights_ready,
        )


class FinalRenderResult(StrictFinalRenderModel):
    version: Literal["final-render-v0.1"] = FINAL_RENDER_VERSION
    project_id: str = Field(min_length=1, max_length=128)
    input_fingerprint: str = Field(min_length=64, max_length=64)
    manifest_artifact_id: str = Field(min_length=1, max_length=128)
    human_review_artifact_id: str = Field(min_length=1, max_length=128)
    human_review: HumanFinalReviewRecord
    video_base_manifest_artifact_id: str = Field(min_length=1, max_length=128)
    audio_bundle_artifact_id: str = Field(min_length=1, max_length=128)
    media_resolution_artifact_id: str = Field(min_length=1, max_length=128)
    subtitle_artifact_id: str = Field(min_length=1, max_length=128)
    subtitle_sha256: str = Field(min_length=64, max_length=64)
    master: FinalRenderArtifact
    social: FinalRenderArtifact
    rights_provenance: dict[str, Any] = Field(default_factory=dict)
    post_review_content_mutation: bool = False
    auto_publication: bool = False
    reused: bool = False
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_result(self):
        if self.human_review.decision != HumanFinalReviewDecision.APPROVE:
            raise ValueError("final render requires APPROVE human review")
        if not self.human_review.all_required_gates_passed:
            raise ValueError("final render requires all seven human review gates")
        if self.master.profile_id != MASTER_PROFILE_ID:
            raise ValueError("master profile mismatch")
        if self.social.profile_id != SOCIAL_PROFILE_ID:
            raise ValueError("social profile mismatch")
        if self.post_review_content_mutation:
            raise ValueError("post-review creative content mutation is forbidden")
        if self.auto_publication:
            raise ValueError("automatic publication is forbidden")
        try:
            int(self.input_fingerprint, 16)
            int(self.subtitle_sha256, 16)
        except ValueError as exc:
            raise ValueError("final render hashes must be hexadecimal") from exc
        return self

    def finalization_artifacts(self) -> list[FinalVideoArtifactProbe]:
        return [
            self.master.to_finalization_probe(),
            self.social.to_finalization_probe(),
        ]
