from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictRecoveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RecoveryArtifactKind(str, Enum):
    LOCKFILE = "lockfile"
    CONFIG = "config"
    ASTROMEDIA_DB = "astromedia_db"
    RIGHTS_SIDECAR = "rights_sidecar"
    FACTLOCK = "factlock"
    PROJECT_MANIFEST = "project_manifest"
    DELIVERY_MANIFEST = "delivery_manifest"
    GOLDEN = "golden"
    SBOM = "sbom"
    OTHER = "other"


class RecoveryArtifact(StrictRecoveryModel):
    artifact_id: str = Field(min_length=1)
    kind: RecoveryArtifactKind
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    required: bool = True

    @model_validator(mode="after")
    def relative_path_must_be_safe(self):
        value = self.relative_path.replace("\\", "/")
        if value.startswith("/") or ":" in value.split("/", 1)[0]:
            raise ValueError("recovery artifact path must be relative")
        if any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("recovery artifact path contains unsafe segments")
        return self


class RecoveryManifest(StrictRecoveryModel):
    manifest_version: str = "1"
    release_candidate_sha: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    artifacts: list[RecoveryArtifact] = Field(min_length=1)
    auto_publication: bool = False

    @model_validator(mode="after")
    def validate_manifest(self):
        if self.auto_publication:
            raise ValueError("AUTO_PUBLICATION must remain false")
        ids = [item.artifact_id for item in self.artifacts]
        paths = [item.relative_path.casefold() for item in self.artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("recovery artifact ids must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("recovery artifact paths must be unique")
        return self


class RecoveryVerificationItem(StrictRecoveryModel):
    artifact_id: str
    relative_path: str
    exists: bool
    hash_matches: bool
    actual_sha256: str | None = None


class RecoveryVerificationResult(StrictRecoveryModel):
    release_candidate_sha: str
    verified: bool
    required_total: int = Field(ge=0)
    required_passed: int = Field(ge=0)
    items: list[RecoveryVerificationItem]
    blockers: list[str] = Field(default_factory=list)
