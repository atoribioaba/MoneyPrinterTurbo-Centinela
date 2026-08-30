from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.finalization_e2e import FinalizationE2EPlan

PUBLICATION_PACKAGE_VERSION = "publication-package-v0.2"
SHA256_PATTERN = r"^[A-Fa-f0-9]{64}$"


class StrictPublicationPackageModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class PublicationPackageStatus(str, Enum):
    WAITING_FOR_FINALIZATION = "WAITING_FOR_FINALIZATION"
    WAITING_FOR_METADATA = "WAITING_FOR_METADATA"
    WAITING_FOR_REQUIRED_ASSETS = "WAITING_FOR_REQUIRED_ASSETS"
    READY_FOR_MANUAL_PACKAGE = "READY_FOR_MANUAL_PACKAGE"


class PublicationMetadata(StrictPublicationPackageModel):
    title: str = Field(min_length=1, max_length=200)
    caption: str = Field(min_length=1, max_length=5000)
    hashtags: list[str] = Field(default_factory=list, max_length=50)
    youtube_description: str | None = Field(default=None, max_length=5000)


class PublicationSupportAssetProbe(StrictPublicationPackageModel):
    source_path: str | None = None
    present: bool = False
    sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


class PublicationSupportManifest(StrictPublicationPackageModel):
    thumbnail: PublicationSupportAssetProbe = Field(
        default_factory=PublicationSupportAssetProbe
    )
    subtitles_es: PublicationSupportAssetProbe = Field(
        default_factory=PublicationSupportAssetProbe
    )
    provenance: PublicationSupportAssetProbe = Field(
        default_factory=PublicationSupportAssetProbe
    )
    review_checklist: PublicationSupportAssetProbe = Field(
        default_factory=PublicationSupportAssetProbe
    )


class PackageAsset(StrictPublicationPackageModel):
    asset_id: str
    source_path: str | None = None
    target_filename: str
    required: bool = True
    present: bool = False
    sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    generated_from_metadata: bool = False
    publication_rights_ready: bool = True


class PublicationPackageRequest(StrictPublicationPackageModel):
    finalization: FinalizationE2EPlan
    metadata: PublicationMetadata | None = None
    support: PublicationSupportManifest = Field(default_factory=PublicationSupportManifest)


class PublicationPackagePlan(StrictPublicationPackageModel):
    version: str = PUBLICATION_PACKAGE_VERSION
    source_finalization_e2e_hash: str
    deterministic: bool = True
    planning_only: bool = True
    manual_publication_only: bool = True
    resource_class: str = "LIGHT"
    writes_files: bool = False
    uploads_files: bool = False
    network_calls: int = 0
    webhook_calls: int = 0
    auto_publication: bool = False
    authorization_to_publish: bool = False
    marks_published: bool = False
    human_review_required: bool = True
    local_final_certification_required: bool = True
    status: PublicationPackageStatus
    asset_count: int = Field(ge=0)
    required_asset_count: int = Field(default=0, ge=0)
    present_required_asset_count: int = Field(default=0, ge=0)
    hashed_required_asset_count: int = Field(default=0, ge=0)
    assets: list[PackageAsset]
    metadata_present: bool
    human_review_recorded: bool = False
    finalization_evidence_valid: bool = False
    rights_ready: bool = False
    all_required_assets_present: bool = False
    all_required_assets_hashed: bool = False
    publication_package_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        required = [asset for asset in self.assets if asset.required]
        present_required = [asset for asset in required if asset.present]
        hashed_required = [asset for asset in required if asset.sha256 is not None]
        expected_all_present = bool(required) and len(present_required) == len(required)
        expected_all_hashed = bool(required) and len(hashed_required) == len(required)

        if self.asset_count != len(self.assets):
            raise ValueError("asset_count mismatch")
        if self.required_asset_count != len(required):
            raise ValueError("required_asset_count mismatch")
        if self.present_required_asset_count != len(present_required):
            raise ValueError("present_required_asset_count mismatch")
        if self.hashed_required_asset_count != len(hashed_required):
            raise ValueError("hashed_required_asset_count mismatch")
        if self.all_required_assets_present != expected_all_present:
            raise ValueError("all_required_assets_present mismatch")
        if self.all_required_assets_hashed != expected_all_hashed:
            raise ValueError("all_required_assets_hashed mismatch")

        if (
            not self.planning_only
            or not self.manual_publication_only
            or self.writes_files
            or self.uploads_files
            or self.network_calls
            or self.webhook_calls
            or self.auto_publication
            or self.authorization_to_publish
            or self.marks_published
            or not self.human_review_required
            or not self.local_final_certification_required
        ):
            raise ValueError("publication package safety guardrail violation")

        if self.status == PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE:
            if not (
                self.metadata_present
                and self.human_review_recorded
                and self.finalization_evidence_valid
                and self.rights_ready
                and self.all_required_assets_present
                and self.all_required_assets_hashed
                and self.required_asset_count == 8
            ):
                raise ValueError("canonical publication package readiness violation")

        return self
