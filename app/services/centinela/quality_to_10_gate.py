from __future__ import annotations

from app.models.quality_certification import (
    CertificationEvidence,
    CertificationStatus,
    DimensionCertification,
    DimensionRequirement,
    EvidenceKind,
    QualityToTenReport,
)


def evaluate_dimension(
    requirement: DimensionRequirement,
    evidence: list[CertificationEvidence],
) -> DimensionCertification:
    present = {item.kind for item in evidence}
    missing = sorted(
        requirement.required_evidence_kinds - present,
        key=lambda item: item.value,
    )
    notes: list[str] = []

    if requirement.blockers:
        status = CertificationStatus.BLOCKED
        notes.append("Explicit blockers remain unresolved.")
    elif missing:
        status = CertificationStatus.CLOUD_READY
        notes.append("Mandatory evidence kinds are still missing.")
    elif requirement.requires_physical_pc and not any(
        item.physical_pc for item in evidence
    ):
        status = CertificationStatus.PHYSICAL_EVIDENCE_REQUIRED
        notes.append("Physical-PC evidence is mandatory for this dimension.")
    elif requirement.requires_human_review and not any(
        item.human_review for item in evidence
    ):
        status = CertificationStatus.HUMAN_EVIDENCE_REQUIRED
        notes.append("Human review evidence is mandatory for this dimension.")
    else:
        status = CertificationStatus.CERTIFIED_10

    return DimensionCertification(
        requirement=requirement,
        evidence=evidence,
        status=status,
        missing_evidence_kinds=missing,
        notes=notes,
    )


def build_quality_report(
    *,
    release_candidate_sha: str,
    dimensions: list[tuple[DimensionRequirement, list[CertificationEvidence]]],
) -> QualityToTenReport:
    certifications = [
        evaluate_dimension(requirement, evidence)
        for requirement, evidence in dimensions
    ]
    all_certified = bool(certifications) and all(
        item.status == CertificationStatus.CERTIFIED_10
        for item in certifications
    )
    return QualityToTenReport(
        release_candidate_sha=release_candidate_sha,
        auto_publication=False,
        dimensions=certifications,
        all_dimensions_certified_10=all_certified,
    )


def canonical_quality_requirements() -> list[DimensionRequirement]:
    """Return the complete canonical evidence contract for the 12 V1 dimensions."""
    return [
        DimensionRequirement(
            dimension="astronomy_general",
            required_evidence_kinds={EvidenceKind.TEST, EvidenceKind.WORKFLOW},
        ),
        DimensionRequirement(
            dimension="practical_observation",
            required_evidence_kinds={EvidenceKind.TEST, EvidenceKind.HUMAN_REVIEW},
            requires_human_review=True,
        ),
        DimensionRequirement(
            dimension="astrophotography",
            required_evidence_kinds={EvidenceKind.TEST, EvidenceKind.HUMAN_REVIEW},
            requires_human_review=True,
        ),
        DimensionRequirement(
            dimension="voice_audio_design",
            required_evidence_kinds={
                EvidenceKind.TEST,
                EvidenceKind.ARTIFACT,
                EvidenceKind.HUMAN_REVIEW,
            },
            requires_human_review=True,
        ),
        DimensionRequirement(
            dimension="voice_audio_real",
            required_evidence_kinds={EvidenceKind.BENCHMARK, EvidenceKind.HUMAN_REVIEW},
            requires_physical_pc=True,
            requires_human_review=True,
        ),
        DimensionRequirement(
            dimension="video_render_real",
            required_evidence_kinds={EvidenceKind.HASHED_REPORT, EvidenceKind.ARTIFACT},
            requires_physical_pc=True,
        ),
        DimensionRequirement(
            dimension="windows_physical",
            required_evidence_kinds={EvidenceKind.HASHED_REPORT},
            requires_physical_pc=True,
        ),
        DimensionRequirement(
            dimension="ai_visual_real",
            required_evidence_kinds={EvidenceKind.BENCHMARK, EvidenceKind.HUMAN_REVIEW},
            requires_physical_pc=True,
            requires_human_review=True,
        ),
        DimensionRequirement(
            dimension="ux_product",
            required_evidence_kinds={EvidenceKind.TEST, EvidenceKind.HUMAN_REVIEW},
            requires_human_review=True,
        ),
        DimensionRequirement(
            dimension="governance",
            required_evidence_kinds={EvidenceKind.TEST, EvidenceKind.ARTIFACT},
        ),
        DimensionRequirement(
            dimension="backup_recovery",
            required_evidence_kinds={EvidenceKind.RECOVERY_DRILL, EvidenceKind.HASHED_REPORT},
            requires_physical_pc=True,
        ),
        DimensionRequirement(
            dimension="oss_supply_chain",
            required_evidence_kinds={EvidenceKind.LICENSE, EvidenceKind.ARTIFACT},
        ),
    ]
