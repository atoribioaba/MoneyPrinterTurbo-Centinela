from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.video_base_e2e import VideoBaseE2EPlan

FINALIZATION_E2E_VERSION = "finalization-e2e-v0.2"
REQUIRED_HUMAN_REVIEW_CHECK_IDS = (
    "human_review_approved",
    "review_science",
    "review_visual",
    "review_audio",
    "review_subtitles",
    "review_rights",
    "review_thumbnail",
    "review_copy",
)
REQUIRED_FINAL_RENDER_CHECK_IDS = (
    "master_present",
    "social_present",
    "master_file",
    "master_sha256",
    "master_resolution",
    "master_fps",
    "master_audio",
    "master_subtitles",
    "master_rights",
    "social_file",
    "social_sha256",
    "social_resolution",
    "social_fps",
    "social_audio",
    "social_subtitles",
    "social_rights",
)
REQUIRED_FINALIZATION_CHECK_IDS = (
    *REQUIRED_HUMAN_REVIEW_CHECK_IDS,
    *REQUIRED_FINAL_RENDER_CHECK_IDS,
)
REQUIRED_FINAL_PROFILE_IDS = (
    "MASTER_VERTICAL_2160X3840",
    "SOCIAL_VERTICAL_1080X1920",
)


class StrictFinalizationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class HumanFinalReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REJECT = "REJECT"


class FinalizationE2EStatus(str, Enum):
    WAITING_FOR_VIDEO_BASE_E2E = "WAITING_FOR_VIDEO_BASE_E2E"
    WAITING_FOR_HUMAN_REVIEW = "WAITING_FOR_HUMAN_REVIEW"
    HUMAN_REVIEW_CHANGES_REQUESTED = "HUMAN_REVIEW_CHANGES_REQUESTED"
    HUMAN_REVIEW_REJECTED = "HUMAN_REVIEW_REJECTED"
    WAITING_FOR_FINAL_RENDERS = "WAITING_FOR_FINAL_RENDERS"
    FINALIZATION_E2E_PASS = "FINALIZATION_E2E_PASS"
    FINALIZATION_E2E_FAIL = "FINALIZATION_E2E_FAIL"


class HumanFinalReviewRecord(StrictFinalizationModel):
    decision: HumanFinalReviewDecision
    reviewer_ref: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=1, max_length=1500)
    decided_at_utc: datetime
    science_passed: bool = False
    visual_passed: bool = False
    audio_passed: bool = False
    subtitles_passed: bool = False
    rights_passed: bool = False
    thumbnail_passed: bool = False
    copy_passed: bool = False

    @property
    def all_required_gates_passed(self) -> bool:
        return all(
            (
                self.science_passed,
                self.visual_passed,
                self.audio_passed,
                self.subtitles_passed,
                self.rights_passed,
                self.thumbnail_passed,
                self.copy_passed,
            )
        )


class FinalVideoArtifactProbe(StrictFinalizationModel):
    profile_id: str
    file_path: str
    exists: bool
    sha256: str | None = None
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    fps: float = Field(ge=0)
    codec: str | None = None
    audio_stream_count: int = Field(default=0, ge=0)
    subtitles_ready: bool = False
    publication_rights_ready: bool = False


class FinalizationE2ERequest(StrictFinalizationModel):
    video_base: VideoBaseE2EPlan
    human_review: HumanFinalReviewRecord | None = None
    artifacts: list[FinalVideoArtifactProbe] = Field(default_factory=list)


class FinalizationCheck(StrictFinalizationModel):
    check_id: str
    passed: bool
    detail: str


def _valid_sha256(value: str | None) -> bool:
    if not value or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


class FinalizationE2EPlan(StrictFinalizationModel):
    version: str = FINALIZATION_E2E_VERSION
    source_video_base_e2e_hash: str
    deterministic: bool = True
    verification_only: bool = True
    resource_class: str = "LIGHT"
    renders_video: bool = False
    modifies_media: bool = False
    network_calls: int = 0
    uses_llm: bool = False
    auto_publication: bool = False
    human_review_required: bool = True
    authorization_to_publish: bool = False
    uploads_files: bool = False
    webhook_calls: int = 0
    marks_published: bool = False
    local_final_certification_required: bool = True
    status: FinalizationE2EStatus
    human_review_recorded: bool
    required_profile_count: int = 2
    artifact_count: int = Field(ge=0)
    check_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    checks: list[FinalizationCheck]
    artifacts: list[FinalVideoArtifactProbe]
    finalization_e2e_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.artifact_count != len(self.artifacts):
            raise ValueError("artifact_count mismatch")
        if self.check_count != len(self.checks):
            raise ValueError("check_count mismatch")
        if self.passed_count != sum(check.passed for check in self.checks):
            raise ValueError("passed_count mismatch")
        if self.failed_count != sum(not check.passed for check in self.checks):
            raise ValueError("failed_count mismatch")

        check_by_id: dict[str, FinalizationCheck] = {}
        for check in self.checks:
            if check.check_id in check_by_id:
                raise ValueError(f"duplicate finalization check: {check.check_id}")
            check_by_id[check.check_id] = check

        if self.status == FinalizationE2EStatus.FINALIZATION_E2E_PASS:
            if not self.human_review_recorded:
                raise ValueError("FINALIZATION_E2E_PASS requires recorded human review")
            if self.required_profile_count != len(REQUIRED_FINAL_PROFILE_IDS):
                raise ValueError("FINALIZATION_E2E_PASS requires two canonical profiles")
            if self.artifact_count < len(REQUIRED_FINAL_PROFILE_IDS):
                raise ValueError("FINALIZATION_E2E_PASS requires two final render artifacts")

            missing = [
                check_id
                for check_id in REQUIRED_FINALIZATION_CHECK_IDS
                if check_id not in check_by_id
            ]
            if missing:
                raise ValueError(
                    "FINALIZATION_E2E_PASS missing canonical checks: "
                    + ",".join(missing)
                )
            failed_required = [
                check_id
                for check_id in REQUIRED_FINALIZATION_CHECK_IDS
                if not check_by_id[check_id].passed
            ]
            if failed_required:
                raise ValueError(
                    "FINALIZATION_E2E_PASS has failed canonical checks: "
                    + ",".join(failed_required)
                )
            if self.failed_count != 0 or self.passed_count != self.check_count:
                raise ValueError("FINALIZATION_E2E_PASS requires all checks to pass")

            artifacts_by_profile: dict[str, FinalVideoArtifactProbe] = {}
            for artifact in self.artifacts:
                if artifact.profile_id in artifacts_by_profile:
                    raise ValueError(
                        f"duplicate final render profile: {artifact.profile_id}"
                    )
                artifacts_by_profile[artifact.profile_id] = artifact

            missing_profiles = [
                profile_id
                for profile_id in REQUIRED_FINAL_PROFILE_IDS
                if profile_id not in artifacts_by_profile
            ]
            if missing_profiles:
                raise ValueError(
                    "FINALIZATION_E2E_PASS missing final profiles: "
                    + ",".join(missing_profiles)
                )

            master = artifacts_by_profile["MASTER_VERTICAL_2160X3840"]
            social = artifacts_by_profile["SOCIAL_VERTICAL_1080X1920"]
            required_artifact_contracts = (
                (master, 2160, 3840, "master"),
                (social, 1080, 1920, "social"),
            )
            for artifact, width, height, label in required_artifact_contracts:
                if not artifact.exists:
                    raise ValueError(f"{label} final render must exist")
                if not _valid_sha256(artifact.sha256):
                    raise ValueError(f"{label} final render requires SHA256")
                if artifact.width != width or artifact.height != height:
                    raise ValueError(f"{label} final render resolution mismatch")
                if abs(artifact.fps - 30.0) > 0.05:
                    raise ValueError(f"{label} final render fps mismatch")
                if artifact.audio_stream_count < 1:
                    raise ValueError(f"{label} final render requires audio")
                if not artifact.subtitles_ready:
                    raise ValueError(f"{label} final render requires subtitles")
                if not artifact.publication_rights_ready:
                    raise ValueError(f"{label} final render requires publication rights")

        if (
            not self.verification_only
            or self.renders_video
            or self.modifies_media
            or self.network_calls
            or self.uses_llm
            or self.auto_publication
            or not self.human_review_required
            or self.authorization_to_publish
            or self.uploads_files
            or self.webhook_calls
            or self.marks_published
            or not self.local_final_certification_required
        ):
            raise ValueError("F53/Review guardrail violation")
        return self
