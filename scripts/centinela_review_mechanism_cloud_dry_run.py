from __future__ import annotations

from datetime import datetime, timezone

from app.models.finalization_e2e import (
    FinalVideoArtifactProbe,
    FinalizationE2ERequest,
    FinalizationE2EStatus,
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.models.video_base_e2e import VideoBaseE2EPlan, VideoBaseE2EStatus
from app.services.finalization_e2e import build_finalization_e2e

NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)
REVIEW_FIELDS = (
    "science_passed",
    "visual_passed",
    "audio_passed",
    "subtitles_passed",
    "rights_passed",
    "thumbnail_passed",
    "copy_passed",
)


def _video_base() -> VideoBaseE2EPlan:
    return VideoBaseE2EPlan(
        source_production_orchestrator_hash="synthetic-orchestrator",
        status=VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS,
        real_artifact_present=True,
        check_count=0,
        passed_count=0,
        failed_count=0,
        checks=[],
        video_base_e2e_hash="synthetic-video-base",
        generated_at_utc=NOW,
    )


def _review(**overrides: bool) -> HumanFinalReviewRecord:
    gates = {field: True for field in REVIEW_FIELDS}
    gates.update(overrides)
    return HumanFinalReviewRecord(
        decision=HumanFinalReviewDecision.APPROVE,
        reviewer_ref="cloud-dry-run",
        rationale="Synthetic review mechanism evidence; not publication approval.",
        decided_at_utc=NOW,
        **gates,
    )


def _artifacts() -> list[FinalVideoArtifactProbe]:
    return [
        FinalVideoArtifactProbe(
            profile_id="MASTER_VERTICAL_2160X3840",
            file_path="synthetic/master.mp4",
            exists=True,
            sha256="A" * 64,
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
            sha256="B" * 64,
            width=1080,
            height=1920,
            fps=30.0,
            codec="h264",
            audio_stream_count=1,
            subtitles_ready=True,
            publication_rights_ready=True,
        ),
    ]


def _run(review: HumanFinalReviewRecord):
    return build_finalization_e2e(
        FinalizationE2ERequest(
            video_base=_video_base(),
            human_review=review,
            artifacts=_artifacts(),
        )
    )


def main() -> None:
    passed = _run(_review())
    assert passed.status == FinalizationE2EStatus.FINALIZATION_E2E_PASS
    assert passed.failed_count == 0
    assert passed.human_review_required is True
    assert passed.authorization_to_publish is False
    assert passed.auto_publication is False
    assert passed.uploads_files is False
    assert passed.network_calls == 0
    assert passed.webhook_calls == 0
    assert passed.marks_published is False
    assert passed.local_final_certification_required is True

    for field in REVIEW_FIELDS:
        failed = _run(_review(**{field: False}))
        assert failed.status == FinalizationE2EStatus.FINALIZATION_E2E_FAIL
        assert failed.failed_count == 1

    print("REVIEW_MECHANISM=PASS")
    print("SCIENCE_GATE=FAIL_CLOSED")
    print("VISUAL_GATE=FAIL_CLOSED")
    print("AUDIO_GATE=FAIL_CLOSED")
    print("SUBTITLES_GATE=FAIL_CLOSED")
    print("RIGHTS_GATE=FAIL_CLOSED")
    print("THUMBNAIL_GATE=FAIL_CLOSED")
    print("COPY_GATE=FAIL_CLOSED")
    print("REVIEW_APPROVED=TRUE")
    print("AUTHORIZED_TO_PUBLISH=FALSE")
    print("AUTO_PUBLICATION=FALSE")
    print("UPLOADS_FILES=FALSE")
    print("NETWORK_CALLS=0")
    print("WEBHOOK_CALLS=0")
    print("MARKS_PUBLISHED=FALSE")
    print("HUMAN_REVIEW_REQUIRED=TRUE")
    print("LOCAL_FINAL_CERTIFICATION_REQUIRED=TRUE")
    print("REAL_MEDIA_USED=FALSE")


if __name__ == "__main__":
    main()
