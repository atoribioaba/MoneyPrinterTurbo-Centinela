from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


REVIEW_PUBLICATION_VERSION = "review-publication-v0.1"
REQUIRED_REVIEW_CHECKS = (
    "science_verified",
    "visual_match_verified",
    "audio_quality_verified",
    "subtitle_text_verified",
    "rights_verified",
    "thumbnail_verified",
    "publication_copy_verified",
)
REQUIRED_PUBLICATION_FILES = (
    "master_2160x3840.mp4",
    "social_1080x1920.mp4",
    "thumbnail.jpg",
    "caption-instagram.txt",
    "caption-tiktok.txt",
    "title-youtube.txt",
    "description-youtube.txt",
    "hashtags.txt",
    "metadata.json",
    "provenance.json",
    "licenses.json",
    "review-checklist.json",
    "subtitles-es.srt",
)
PUBLICATION_MANIFEST_FILENAME = "publication-manifest.json"


class StrictReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class PublicationCopyDraft(StrictReviewModel):
    instagram_caption: str = Field(min_length=1, max_length=2200)
    tiktok_caption: str = Field(min_length=1, max_length=2200)
    youtube_title: str = Field(min_length=1, max_length=100)
    youtube_description: str = Field(min_length=1, max_length=5000)
    hashtags: list[str] = Field(min_length=1, max_length=20)


class ReviewPacket(StrictReviewModel):
    version: Literal["review-publication-v0.1"] = REVIEW_PUBLICATION_VERSION
    project_id: str
    subject: str

    final_script_artifact_id: str
    final_script_sha256: str = Field(min_length=64, max_length=64)
    material_selection_artifact_id: str
    material_selection_sha256: str = Field(min_length=64, max_length=64)
    media_resolution_artifact_id: str
    media_resolution_sha256: str = Field(min_length=64, max_length=64)
    audio_bundle_artifact_id: str
    audio_bundle_sha256: str = Field(min_length=64, max_length=64)
    video_base_manifest_artifact_id: str
    video_base_manifest_sha256: str = Field(min_length=64, max_length=64)

    review_preview_artifact_id: str
    review_preview_sha256: str = Field(min_length=64, max_length=64)
    subtitle_artifact_id: str
    subtitle_sha256: str = Field(min_length=64, max_length=64)
    thumbnail_candidate_artifact_id: str
    thumbnail_candidate_sha256: str = Field(min_length=64, max_length=64)
    review_copy_draft_artifact_id: str
    review_copy_draft_sha256: str = Field(min_length=64, max_length=64)

    publication_copy: PublicationCopyDraft
    rights_scene_count: int = Field(ge=1)
    publication_eligible_scene_count: int = Field(ge=0)
    license_gate_passed: bool
    approval_available: bool
    primary_source_verification_required: bool
    required_checks: list[str] = Field(min_length=7, max_length=7)

    auto_publication: bool = False
    publication_authorized: bool = False
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_packet(self):
        if self.publication_eligible_scene_count > self.rights_scene_count:
            raise ValueError("publication eligible count exceeds scene count")
        if self.required_checks != list(REQUIRED_REVIEW_CHECKS):
            raise ValueError("review checks do not match canonical R8 contract")
        if self.approval_available != self.license_gate_passed:
            raise ValueError("approval availability must follow hard license gate")
        if self.auto_publication or self.publication_authorized:
            raise ValueError("R8 review packet may not authorize publication")
        return self


class HumanReviewChecklist(StrictReviewModel):
    version: Literal["review-publication-v0.1"] = REVIEW_PUBLICATION_VERSION
    project_id: str
    review_packet_artifact_id: str
    review_packet_sha256: str = Field(min_length=64, max_length=64)
    reviewer: str = Field(min_length=1, max_length=128)
    notes: str = Field(min_length=1, max_length=4000)
    approved: bool

    science_verified: bool = False
    visual_match_verified: bool = False
    audio_quality_verified: bool = False
    subtitle_text_verified: bool = False
    rights_verified: bool = False
    thumbnail_verified: bool = False
    publication_copy_verified: bool = False

    explicit_human_decision: bool = True
    publication_authorized: bool = False
    auto_publication: bool = False
    reviewed_at_utc: datetime

    @property
    def all_checks_passed(self) -> bool:
        return all(bool(getattr(self, name)) for name in REQUIRED_REVIEW_CHECKS)

    @model_validator(mode="after")
    def validate_approval(self):
        if not self.explicit_human_decision:
            raise ValueError("review must be an explicit human decision")
        if self.approved and not self.all_checks_passed:
            raise ValueError("approval requires every canonical review check")
        if self.publication_authorized or self.auto_publication:
            raise ValueError("content approval is not publication authorization")
        return self


class PublicationFile(StrictReviewModel):
    name: str = Field(min_length=1, max_length=128)
    sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)


class PublicationPackageManifest(StrictReviewModel):
    version: Literal["review-publication-v0.1"] = REVIEW_PUBLICATION_VERSION
    project_id: str
    subject: str
    approval_artifact_id: str
    review_checklist_artifact_id: str
    review_packet_artifact_id: str
    package_zip_artifact_id: str
    package_zip_sha256: str = Field(min_length=64, max_length=64)

    source_final_script_sha256: str = Field(min_length=64, max_length=64)
    source_audio_bundle_sha256: str = Field(min_length=64, max_length=64)
    source_video_base_manifest_sha256: str = Field(min_length=64, max_length=64)
    source_material_selection_sha256: str = Field(min_length=64, max_length=64)
    source_media_resolution_sha256: str = Field(min_length=64, max_length=64)

    files: list[PublicationFile] = Field(min_length=13, max_length=13)
    manifest_filename: Literal["publication-manifest.json"] = PUBLICATION_MANIFEST_FILENAME
    provenance_complete: bool
    license_review_complete: bool
    publication_authorized: bool = False
    auto_publication: bool = False
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_package(self):
        names = [item.name for item in self.files]
        if len(set(names)) != len(names):
            raise ValueError("publication package filenames must be unique")
        if set(names) != set(REQUIRED_PUBLICATION_FILES):
            raise ValueError("publication package file set does not match canonical contract")
        if not self.provenance_complete or not self.license_review_complete:
            raise ValueError("publication package requires complete provenance/license review")
        if self.publication_authorized or self.auto_publication:
            raise ValueError("R8 package must remain manual-publication only")
        return self
