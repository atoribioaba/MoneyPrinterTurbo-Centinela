import pytest

from app.models.quality_certification import (
    CertificationEvidence,
    CertificationStatus,
    DimensionCertification,
    DimensionRequirement,
    EvidenceKind,
    QualityToTenReport,
)
from app.services.centinela.quality_to_10_gate import (
    build_quality_report,
    canonical_quality_requirements,
    evaluate_dimension,
)


_SHA40 = "a" * 40
_SHA256 = "b" * 64


def _evidence(kind, *, physical=False, human=False):
    return CertificationEvidence(
        evidence_id=f"e-{kind.value}",
        kind=kind,
        ref=f"fixture:{kind.value}",
        sha256=_SHA256 if kind in {EvidenceKind.HASHED_REPORT, EvidenceKind.ARTIFACT} else None,
        description="fixture evidence",
        physical_pc=physical,
        human_review=human,
    )


def test_physical_dimension_cannot_be_certified_from_cloud_evidence_only():
    requirement = DimensionRequirement(
        dimension="windows_physical",
        required_evidence_kinds={EvidenceKind.HASHED_REPORT},
        requires_physical_pc=True,
    )
    result = evaluate_dimension(requirement, [_evidence(EvidenceKind.HASHED_REPORT)])
    assert result.status == CertificationStatus.PHYSICAL_EVIDENCE_REQUIRED


def test_human_review_dimension_cannot_be_certified_without_human_evidence():
    requirement = DimensionRequirement(
        dimension="ux_product",
        required_evidence_kinds={EvidenceKind.TEST, EvidenceKind.HUMAN_REVIEW},
        requires_human_review=True,
    )
    result = evaluate_dimension(
        requirement,
        [_evidence(EvidenceKind.TEST), _evidence(EvidenceKind.HUMAN_REVIEW)],
    )
    assert result.status == CertificationStatus.HUMAN_EVIDENCE_REQUIRED


def test_complete_physical_and_human_evidence_can_reach_certified_10():
    requirement = DimensionRequirement(
        dimension="voice_audio_real",
        required_evidence_kinds={EvidenceKind.BENCHMARK, EvidenceKind.HUMAN_REVIEW},
        requires_physical_pc=True,
        requires_human_review=True,
    )
    result = evaluate_dimension(
        requirement,
        [
            _evidence(EvidenceKind.BENCHMARK, physical=True),
            _evidence(EvidenceKind.HUMAN_REVIEW, human=True),
        ],
    )
    assert result.status == CertificationStatus.CERTIFIED_10


def test_model_rejects_forged_certified_10_with_missing_evidence():
    requirement = DimensionRequirement(
        dimension="video",
        required_evidence_kinds={EvidenceKind.ARTIFACT},
        requires_physical_pc=True,
    )
    with pytest.raises(ValueError, match="mandatory evidence"):
        DimensionCertification(
            requirement=requirement,
            evidence=[],
            status=CertificationStatus.CERTIFIED_10,
        )


def test_report_rejects_auto_publication_and_false_summary():
    requirement = DimensionRequirement(dimension="governance")
    certified = evaluate_dimension(requirement, [])
    assert certified.status == CertificationStatus.CERTIFIED_10

    with pytest.raises(ValueError, match="AUTO_PUBLICATION"):
        QualityToTenReport(
            release_candidate_sha=_SHA40,
            auto_publication=True,
            dimensions=[certified],
            all_dimensions_certified_10=True,
        )

    with pytest.raises(ValueError, match="must match"):
        QualityToTenReport(
            release_candidate_sha=_SHA40,
            auto_publication=False,
            dimensions=[certified],
            all_dimensions_certified_10=False,
        )


def test_canonical_requirements_keep_runtime_dimensions_physical():
    requirements = {item.dimension: item for item in canonical_quality_requirements()}
    for dimension in (
        "voice_audio_real",
        "video_render_real",
        "windows_physical",
        "ai_visual_real",
        "backup_recovery",
    ):
        assert requirements[dimension].requires_physical_pc is True


def test_quality_report_computes_summary_from_evidence():
    requirement = DimensionRequirement(
        dimension="astronomy",
        required_evidence_kinds={EvidenceKind.TEST},
    )
    report = build_quality_report(
        release_candidate_sha=_SHA40,
        dimensions=[(requirement, [_evidence(EvidenceKind.TEST)])],
    )
    assert report.all_dimensions_certified_10 is True
    assert report.dimensions[0].status == CertificationStatus.CERTIFIED_10
