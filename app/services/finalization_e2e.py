from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.finalization_e2e import (
    FINALIZATION_E2E_VERSION,
    FinalizationCheck,
    FinalizationE2EPlan,
    FinalizationE2ERequest,
    FinalizationE2EStatus,
    HumanFinalReviewDecision,
)
from app.models.video_base_e2e import VideoBaseE2EStatus


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest().upper()


def build_finalization_e2e(request: FinalizationE2ERequest) -> FinalizationE2EPlan:
    checks: list[FinalizationCheck] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append(
            FinalizationCheck(check_id=check_id, passed=passed, detail=detail)
        )

    if request.video_base.status != VideoBaseE2EStatus.VIDEO_BASE_E2E_PASS:
        status = FinalizationE2EStatus.WAITING_FOR_VIDEO_BASE_E2E
    elif request.human_review is None:
        status = FinalizationE2EStatus.WAITING_FOR_HUMAN_REVIEW
    else:
        review = request.human_review
        approved = review.decision == HumanFinalReviewDecision.APPROVE
        check("human_review_approved", approved, review.decision.value)

        if not approved:
            status = FinalizationE2EStatus.HUMAN_REVIEW_REJECTED
        else:
            review_gates = (
                ("review_science", review.science_passed, "science"),
                ("review_visual", review.visual_passed, "visual"),
                ("review_audio", review.audio_passed, "audio"),
                ("review_subtitles", review.subtitles_passed, "subtitles"),
                ("review_rights", review.rights_passed, "rights"),
                ("review_thumbnail", review.thumbnail_passed, "thumbnail"),
                ("review_copy", review.copy_passed, "copy"),
            )
            for check_id, passed, detail in review_gates:
                check(check_id, passed, detail)

            if not review.all_required_gates_passed:
                status = FinalizationE2EStatus.FINALIZATION_E2E_FAIL
            elif not request.artifacts:
                status = FinalizationE2EStatus.WAITING_FOR_FINAL_RENDERS
            else:
                profiles = {artifact.profile_id: artifact for artifact in request.artifacts}
                master = profiles.get("MASTER_VERTICAL_2160X3840")
                social = profiles.get("SOCIAL_VERTICAL_1080X1920")
                check(
                    "master_present",
                    master is not None,
                    "MASTER_VERTICAL_2160X3840",
                )
                check(
                    "social_present",
                    social is not None,
                    "SOCIAL_VERTICAL_1080X1920",
                )
                if master:
                    check("master_file", master.exists, master.file_path)
                    check(
                        "master_resolution",
                        master.width == 2160 and master.height == 3840,
                        f"{master.width}x{master.height}",
                    )
                    check("master_fps", abs(master.fps - 30) <= 0.05, str(master.fps))
                    check(
                        "master_audio",
                        master.audio_stream_count >= 1,
                        str(master.audio_stream_count),
                    )
                    check(
                        "master_subtitles",
                        master.subtitles_ready,
                        str(master.subtitles_ready),
                    )
                    check(
                        "master_rights",
                        master.publication_rights_ready,
                        str(master.publication_rights_ready),
                    )
                if social:
                    check("social_file", social.exists, social.file_path)
                    check(
                        "social_resolution",
                        social.width == 1080 and social.height == 1920,
                        f"{social.width}x{social.height}",
                    )
                    check("social_fps", abs(social.fps - 30) <= 0.05, str(social.fps))
                    check(
                        "social_audio",
                        social.audio_stream_count >= 1,
                        str(social.audio_stream_count),
                    )
                    check(
                        "social_subtitles",
                        social.subtitles_ready,
                        str(social.subtitles_ready),
                    )
                    check(
                        "social_rights",
                        social.publication_rights_ready,
                        str(social.publication_rights_ready),
                    )
                status = (
                    FinalizationE2EStatus.FINALIZATION_E2E_PASS
                    if checks and all(item.passed for item in checks)
                    else FinalizationE2EStatus.FINALIZATION_E2E_FAIL
                )

    stable = {
        "version": FINALIZATION_E2E_VERSION,
        "video_base": request.video_base.video_base_e2e_hash,
        "review": (
            request.human_review.model_dump(mode="json")
            if request.human_review
            else None
        ),
        "artifacts": [
            artifact.model_dump(mode="json") for artifact in request.artifacts
        ],
        "status": status.value,
        "checks": [item.model_dump(mode="json") for item in checks],
    }
    return FinalizationE2EPlan(
        source_video_base_e2e_hash=request.video_base.video_base_e2e_hash,
        status=status,
        human_review_recorded=request.human_review is not None,
        artifact_count=len(request.artifacts),
        check_count=len(checks),
        passed_count=sum(item.passed for item in checks),
        failed_count=sum(not item.passed for item in checks),
        checks=checks,
        artifacts=request.artifacts,
        finalization_e2e_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
