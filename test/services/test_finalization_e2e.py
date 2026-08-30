from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.finalization_e2e import (
    REQUIRED_HUMAN_REVIEW_CHECK_IDS,
    FinalVideoArtifactProbe,
    FinalizationCheck,
    FinalizationE2EPlan,
    FinalizationE2ERequest,
    FinalizationE2EStatus,
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.models.video_base_e2e import VideoBaseE2EPlan, VideoBaseE2EStatus
from app.services.finalization_e2e import build_finalization_e2e

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)
HASH_A = "A" * 64
HASH_B = "B" * 64
REVIEW_FIELDS = (
    "science_passed",
    "visual_passed",
    "audio_passed",
    "subtitles_passed",
    "rights_passed",
    "thumbnail_passed",
    "copy_passed",
)


def base(status=VideoBaseE2EStatus.WAITING_FOR_REAL_VIDEO_BASE):
    return VideoBaseE2EPlan(
        source_production_orchestrator_hash="o",
        status=status,
        real_artifact_present=status == VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS,
        check_count=0,
        passed_count=0,
        failed_count=0,
        checks=[],
        video_base_e2e_hash="b",
        generated_at_utc=NOW,
    )


def review(*, decision=HumanFinalReviewDecision.APPROVE, **overrides):
    gates = {field: True for field in REVIEW_FIELDS}
    gates.update(overrides)
    return HumanFinalReviewRecord(
        decision=decision,
        reviewer_ref="synthetic-reviewer",
        rationale="Synthetic cloud contract evidence only.",
        decided_at_utc=NOW,
        **gates,
    )


def artifacts():
    return [
        FinalVideoArtifactProbe(
            profile_id="MASTER_VERTICAL_2160X3840",
            file_path="synthetic/master.mp4",
            exists=True,
            sha256=HASH_A,
            width=2160,
            height=3840,
            fps=30.0,
            codec="h264",
            audio_stream_count=1,
            subtitles_ready=True,
            publication_rights_ready=True,
        ),
        FinalVideoArtifactProbe(
            profile_id="SOCIAL_VERTICAL_1080X1920",
            file_path="synthetic/social.mp4",
            exists=True,
            sha256=HASH_B,
            width=1080,
            height=1920,
            fps=30.0,
            codec="h264",
            audio_stream_count=1,
            subtitles_ready=True,
            publication_rights_ready=True,
        ),
    ]


def test_cannot_skip_real_video_base():
    result = build_finalization_e2e(FinalizationE2ERequest(video_base=base()))
    assert result.status == FinalizationE2EStatus.WAITING_FOR_VIDEO_BASE_E2E
    assert result.renders_video is False


def test_passed_base_still_requires_human_review():
    result = build_finalization_e2e(
        FinalizationE2ERequest(
            video_base=base(VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS)
        )
    )
    assert result.status == FinalizationE2EStatus.WAITING_FOR_HUMAN_REVIEW
    assert result.human_review_required is True


def test_rejected_review_stays_rejected():
    result = build_finalization_e2e(
        FinalizationE2ERequest(
            video_base=base(VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS),
            human_review=review(decision=HumanFinalReviewDecision.REJECT),
            artifacts=artifacts(),
        )
    )
    assert result.status == FinalizationE2EStatus.HUMAN_REVIEW_REJECTED
    assert result.finalization_e2e_hash


def test_all_seven_review_gates_and_artifacts_can_pass():
    result = build_finalization_e2e(
        FinalizationE2ERequest(
            video_base=base(VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS),
            human_review=review(),
            artifacts=artifacts(),
        )
    )
    assert result.status == FinalizationE2EStatus.FINALIZATION_E2E_PASS
    checks = {item.check_id: item for item in result.checks}
    for check_id in (
        "human_review_approved",
        "review_science",
        "review_visual",
        "review_audio",
        "review_subtitles",
        "review_rights",
        "review_thumbnail",
        "review_copy",
        "master_sha256",
        "social_sha256",
    ):
        assert checks[check_id].passed is True
    assert result.failed_count == 0


@pytest.mark.parametrize("field", REVIEW_FIELDS)
def test_each_missing_review_dimension_fails_closed(field):
    result = build_finalization_e2e(
        FinalizationE2ERequest(
            video_base=base(VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS),
            human_review=review(**{field: False}),
            artifacts=artifacts(),
        )
    )
    assert result.status == FinalizationE2EStatus.FINALIZATION_E2E_FAIL
    assert result.failed_count == 1


def test_legacy_approve_without_gate_evidence_fails_closed():
    legacy_review = HumanFinalReviewRecord(
        decision=HumanFinalReviewDecision.APPROVE,
        reviewer_ref="legacy-reviewer",
        rationale="Legacy approval without explicit gate evidence.",
        decided_at_utc=NOW,
    )
    result = build_finalization_e2e(
        FinalizationE2ERequest(
            video_base=base(VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS),
            human_review=legacy_review,
            artifacts=artifacts(),
        )
    )
    assert result.status == FinalizationE2EStatus.FINALIZATION_E2E_FAIL
    assert result.failed_count == 7


def test_missing_final_render_sha_fails_closed():
    probes = artifacts()
    probes[0].sha256 = None
    result = build_finalization_e2e(
        FinalizationE2ERequest(
            video_base=base(VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS),
            human_review=review(),
            artifacts=probes,
        )
    )
    assert result.status == FinalizationE2EStatus.FINALIZATION_E2E_FAIL
    checks = {item.check_id: item for item in result.checks}
    assert checks["master_sha256"].passed is False


def test_approved_review_does_not_authorize_publication():
    result = build_finalization_e2e(
        FinalizationE2ERequest(
            video_base=base(VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS),
            human_review=review(),
            artifacts=artifacts(),
        )
    )
    assert result.status == FinalizationE2EStatus.FINALIZATION_E2E_PASS
    assert result.authorization_to_publish is False
    assert result.auto_publication is False
    assert result.uploads_files is False
    assert result.network_calls == 0
    assert result.webhook_calls == 0
    assert result.marks_published is False
    assert result.local_final_certification_required is True


def test_forged_pass_without_canonical_review_checks_is_rejected():
    with pytest.raises(ValidationError):
        FinalizationE2EPlan(
            source_video_base_e2e_hash="b",
            status=FinalizationE2EStatus.FINALIZATION_E2E_PASS,
            human_review_recorded=True,
            artifact_count=0,
            check_count=1,
            passed_count=1,
            failed_count=0,
            checks=[
                FinalizationCheck(
                    check_id="generic_approved",
                    passed=True,
                    detail="insufficient synthetic evidence",
                )
            ],
            artifacts=[],
            finalization_e2e_hash="F" * 64,
            generated_at_utc=NOW,
        )


def test_forged_pass_with_review_only_but_no_final_renders_is_rejected():
    checks = [
        FinalizationCheck(check_id=check_id, passed=True, detail="review only")
        for check_id in REQUIRED_HUMAN_REVIEW_CHECK_IDS
    ]
    with pytest.raises(ValidationError, match="two final render artifacts"):
        FinalizationE2EPlan(
            source_video_base_e2e_hash="b",
            status=FinalizationE2EStatus.FINALIZATION_E2E_PASS,
            human_review_recorded=True,
            artifact_count=0,
            check_count=len(checks),
            passed_count=len(checks),
            failed_count=0,
            checks=checks,
            artifacts=[],
            finalization_e2e_hash="F" * 64,
            generated_at_utc=NOW,
        )


def test_pass_plan_cannot_enable_publication_side_effects():
    result = build_finalization_e2e(
        FinalizationE2ERequest(
            video_base=base(VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS),
            human_review=review(),
            artifacts=artifacts(),
        )
    )
    payload = result.model_dump(mode="json")
    payload["authorization_to_publish"] = True
    with pytest.raises(ValidationError):
        FinalizationE2EPlan.model_validate(payload)
