from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.finalization_e2e import (
    REQUIRED_HUMAN_REVIEW_CHECK_IDS,
    FinalVideoArtifactProbe,
    FinalizationCheck,
    FinalizationE2EPlan,
    FinalizationE2EStatus,
)
from app.models.publication_package import (
    PublicationMetadata,
    PublicationPackagePlan,
    PublicationPackageRequest,
    PublicationPackageStatus,
    PublicationSupportAssetProbe,
    PublicationSupportManifest,
)
from app.services.publication_package import build_publication_package

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)
HASH_A = "A" * 64
HASH_B = "B" * 64
HASH_C = "C" * 64
HASH_D = "D" * 64
HASH_E = "E" * 64
HASH_F = "F" * 64


def waiting_finalization():
    return FinalizationE2EPlan(
        source_video_base_e2e_hash="b",
        status=FinalizationE2EStatus.WAITING_FOR_VIDEO_BASE_E2E,
        human_review_recorded=False,
        artifact_count=0,
        check_count=0,
        passed_count=0,
        failed_count=0,
        checks=[],
        artifacts=[],
        finalization_e2e_hash="f",
        generated_at_utc=NOW,
    )


def passed_finalization(*, human_review_recorded=True, rights_ready=True, social_hash=HASH_B):
    artifacts = [
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
            publication_rights_ready=rights_ready,
        ),
        FinalVideoArtifactProbe(
            profile_id="SOCIAL_VERTICAL_1080X1920",
            file_path="synthetic/social.mp4",
            exists=True,
            sha256=social_hash,
            width=1080,
            height=1920,
            fps=30.0,
            codec="h264",
            audio_stream_count=1,
            subtitles_ready=True,
            publication_rights_ready=rights_ready,
        ),
    ]
    checks = [
        FinalizationCheck(
            check_id=check_id,
            passed=True,
            detail="synthetic canonical review evidence",
        )
        for check_id in REQUIRED_HUMAN_REVIEW_CHECK_IDS
    ]
    checks.append(
        FinalizationCheck(
            check_id="final_renders_verified",
            passed=True,
            detail="synthetic render evidence",
        )
    )
    plan = FinalizationE2EPlan(
        source_video_base_e2e_hash="b",
        status=FinalizationE2EStatus.FINALIZATION_E2E_PASS,
        human_review_recorded=True,
        artifact_count=len(artifacts),
        check_count=len(checks),
        passed_count=len(checks),
        failed_count=0,
        checks=checks,
        artifacts=artifacts,
        finalization_e2e_hash="F" * 64,
        generated_at_utc=NOW,
    )
    if not human_review_recorded:
        return plan.model_copy(update={"human_review_recorded": False})
    return plan


def metadata():
    return PublicationMetadata(
        title="Sol a Luna",
        caption="Del último resplandor solar al cielo nocturno.",
        hashtags=["#astronomia", "#luna"],
        youtube_description="Fixture determinista del Publication Package v0.2.",
    )


def probe(path, sha):
    return PublicationSupportAssetProbe(
        source_path=path,
        present=True,
        sha256=sha,
    )


def support():
    return PublicationSupportManifest(
        thumbnail=probe("synthetic/thumbnail.jpg", HASH_C),
        subtitles_es=probe("synthetic/subtitles-es.srt", HASH_D),
        provenance=probe("synthetic/provenance.json", HASH_E),
        review_checklist=probe("synthetic/review-checklist.json", HASH_F),
    )


def ready_request():
    return PublicationPackageRequest(
        finalization=passed_finalization(),
        metadata=metadata(),
        support=support(),
    )


def test_waits_for_finalization():
    result = build_publication_package(
        PublicationPackageRequest(finalization=waiting_finalization())
    )
    assert result.status == PublicationPackageStatus.WAITING_FOR_FINALIZATION
    assert result.auto_publication is False
    assert result.uploads_files is False
    assert result.network_calls == 0


def test_waits_for_metadata_after_valid_finalization():
    result = build_publication_package(
        PublicationPackageRequest(finalization=passed_finalization())
    )
    assert result.status == PublicationPackageStatus.WAITING_FOR_METADATA


def test_missing_thumbnail_fails_closed():
    request = ready_request()
    request.support.thumbnail = PublicationSupportAssetProbe()
    result = build_publication_package(request)
    assert result.status == PublicationPackageStatus.WAITING_FOR_REQUIRED_ASSETS


def test_missing_subtitles_fails_closed():
    request = ready_request()
    request.support.subtitles_es = PublicationSupportAssetProbe()
    result = build_publication_package(request)
    assert result.status == PublicationPackageStatus.WAITING_FOR_REQUIRED_ASSETS


def test_missing_provenance_fails_closed():
    request = ready_request()
    request.support.provenance = PublicationSupportAssetProbe()
    result = build_publication_package(request)
    assert result.status == PublicationPackageStatus.WAITING_FOR_REQUIRED_ASSETS
    assert result.rights_ready is False


def test_missing_review_checklist_fails_closed():
    request = ready_request()
    request.support.review_checklist = PublicationSupportAssetProbe()
    result = build_publication_package(request)
    assert result.status == PublicationPackageStatus.WAITING_FOR_REQUIRED_ASSETS


def test_missing_video_hash_fails_closed():
    request = PublicationPackageRequest(
        finalization=passed_finalization(social_hash=None),
        metadata=metadata(),
        support=support(),
    )
    result = build_publication_package(request)
    assert result.status == PublicationPackageStatus.WAITING_FOR_REQUIRED_ASSETS
    assert result.all_required_assets_hashed is False


def test_video_rights_not_ready_fails_closed():
    request = PublicationPackageRequest(
        finalization=passed_finalization(rights_ready=False),
        metadata=metadata(),
        support=support(),
    )
    result = build_publication_package(request)
    assert result.status == PublicationPackageStatus.WAITING_FOR_REQUIRED_ASSETS
    assert result.rights_ready is False


def test_forged_pass_without_human_review_is_rejected_before_packaging():
    with pytest.raises(ValidationError):
        PublicationPackageRequest(
            finalization=passed_finalization(human_review_recorded=False),
            metadata=metadata(),
            support=support(),
        )


def test_forged_pass_missing_review_dimension_is_rejected_before_packaging():
    finalization = passed_finalization()
    forged_checks = [
        check for check in finalization.checks if check.check_id != "review_science"
    ]
    forged = finalization.model_copy(
        update={
            "checks": forged_checks,
            "check_count": len(forged_checks),
            "passed_count": len(forged_checks),
        }
    )
    with pytest.raises(ValidationError):
        PublicationPackageRequest(
            finalization=forged,
            metadata=metadata(),
            support=support(),
        )


def test_ready_requires_all_eight_assets_with_hashes():
    result = build_publication_package(ready_request())
    assert result.status == PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE
    assert result.asset_count == 8
    assert result.required_asset_count == 8
    assert result.present_required_asset_count == 8
    assert result.hashed_required_asset_count == 8
    assert result.all_required_assets_present is True
    assert result.all_required_assets_hashed is True
    assert result.rights_ready is True
    assert {asset.target_filename for asset in result.assets} == {
        "master_2160x3840.mp4",
        "social_1080x1920.mp4",
        "thumbnail.jpg",
        "subtitles-es.srt",
        "caption.txt",
        "metadata.json",
        "sources-licenses-provenance.json",
        "publication-checklist.json",
    }
    assert all(asset.sha256 and len(asset.sha256) == 64 for asset in result.assets)
    assert result.planning_only is True
    assert result.manual_publication_only is True
    assert result.writes_files is False
    assert result.uploads_files is False
    assert result.network_calls == 0
    assert result.webhook_calls == 0
    assert result.auto_publication is False
    assert result.authorization_to_publish is False
    assert result.marks_published is False
    assert result.local_final_certification_required is True


def test_package_hash_is_deterministic_for_identical_stable_input():
    first = build_publication_package(ready_request())
    second = build_publication_package(ready_request())
    assert first.publication_package_hash == second.publication_package_hash


def test_strict_support_probe_rejects_extra_fields():
    with pytest.raises(ValidationError):
        PublicationSupportAssetProbe.model_validate(
            {
                "source_path": "synthetic/x",
                "present": True,
                "sha256": HASH_A,
                "unexpected": True,
            }
        )


def test_ready_plan_cannot_enable_publication_side_effects():
    ready = build_publication_package(ready_request())
    payload = ready.model_dump(mode="json")
    payload["auto_publication"] = True
    with pytest.raises(ValidationError):
        PublicationPackagePlan.model_validate(payload)
