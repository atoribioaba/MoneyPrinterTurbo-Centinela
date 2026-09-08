from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictQualityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CertificationStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    CLOUD_READY = "CLOUD_READY"
    PHYSICAL_EVIDENCE_REQUIRED = "PHYSICAL_EVIDENCE_REQUIRED"
    HUMAN_EVIDENCE_REQUIRED = "HUMAN_EVIDENCE_REQUIRED"
    BLOCKED = "BLOCKED"
    CERTIFIED_10 = "CERTIFIED_10"


class EvidenceKind(str, Enum):
    TEST = "test"
    WORKFLOW = "workflow"
    LOG = "log"
    HASHED_REPORT = "hashed_report"
    ARTIFACT = "artifact"
    HUMAN_REVIEW = "human_review"
    LICENSE = "license"
    BENCHMARK = "benchmark"
    RECOVERY_DRILL = "recovery_drill"


class CertificationEvidence(StrictQualityModel):
    evidence_id: str = Field(min_length=1)
    kind: EvidenceKind
    ref: str = Field(min_length=1)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    description: str = Field(min_length=1)
    physical_pc: bool = False
    human_review: bool = False


class DimensionRequirement(StrictQualityModel):
    dimension: str = Field(min_length=1)
    target_score: float = Field(default=10.0, ge=0.0, le=10.0)
    required_evidence_kinds: set[EvidenceKind] = Field(default_factory=set)
    requires_physical_pc: bool = False
    requires_human_review: bool = False
    blockers: list[str] = Field(default_factory=list)


class DimensionCertification(StrictQualityModel):
    requirement: DimensionRequirement
    evidence: list[CertificationEvidence] = Field(default_factory=list)
    status: CertificationStatus
    missing_evidence_kinds: list[EvidenceKind] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def certified_ten_requires_complete_evidence(self):
        if self.status != CertificationStatus.CERTIFIED_10:
            return self
        if self.requirement.blockers:
            raise ValueError("CERTIFIED_10 cannot have blockers")
        present = {item.kind for item in self.evidence}
        missing = self.requirement.required_evidence_kinds - present
        if missing:
            raise ValueError("CERTIFIED_10 requires every mandatory evidence kind")
        if self.requirement.requires_physical_pc and not any(
            item.physical_pc for item in self.evidence
        ):
            raise ValueError("CERTIFIED_10 requires physical PC evidence")
        if self.requirement.requires_human_review and not any(
            item.human_review for item in self.evidence
        ):
            raise ValueError("CERTIFIED_10 requires human review evidence")
        return self


class QualityToTenReport(StrictQualityModel):
    release_candidate_sha: str = Field(pattern=r"^[0-9a-fA-F]{40}$")
    auto_publication: bool = False
    dimensions: list[DimensionCertification]
    all_dimensions_certified_10: bool

    @model_validator(mode="after")
    def protect_publication_and_summary(self):
        if self.auto_publication:
            raise ValueError("AUTO_PUBLICATION must remain false")
        computed = bool(self.dimensions) and all(
            item.status == CertificationStatus.CERTIFIED_10 for item in self.dimensions
        )
        if self.all_dimensions_certified_10 != computed:
            raise ValueError("all_dimensions_certified_10 must match dimension statuses")
        return self
