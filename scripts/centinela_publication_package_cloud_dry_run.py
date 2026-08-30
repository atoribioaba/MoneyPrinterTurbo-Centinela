from datetime import datetime, timezone

from app.models.finalization_e2e import (
    REQUIRED_HUMAN_REVIEW_CHECK_IDS,
    FinalVideoArtifactProbe,
    FinalizationCheck,
    FinalizationE2EPlan,
    FinalizationE2EStatus,
)
from app.models.publication_package import (
    PublicationMetadata,
    PublicationPackageRequest,
    PublicationPackageStatus,
    PublicationSupportAssetProbe,
    PublicationSupportManifest,
)
from app.services.publication_package import build_publication_package

NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


def probe(path: str, character: str) -> PublicationSupportAssetProbe:
    return PublicationSupportAssetProbe(
        source_path=path,
        present=True,
        sha256=character * 64,
    )


def finalization() -> FinalizationE2EPlan:
    artifacts = [
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
            detail="synthetic fixture",
        )
    )
    return FinalizationE2EPlan(
        source_video_base_e2e_hash="C" * 64,
        status=FinalizationE2EStatus.FINALIZATION_E2E_PASS,
        human_review_recorded=True,
        artifact_count=2,
        check_count=len(checks),
        passed_count=len(checks),
        failed_count=0,
        checks=checks,
        artifacts=artifacts,
        finalization_e2e_hash="D" * 64,
        generated_at_utc=NOW,
    )


def main() -> None:
    request = PublicationPackageRequest(
        finalization=finalization(),
        metadata=PublicationMetadata(
            title="Synthetic SOL_TO_MOON fixture",
            caption="Synthetic publication package fixture.",
            hashtags=["#astronomia"],
            youtube_description="Synthetic cloud-only fixture.",
        ),
        support=PublicationSupportManifest(
            thumbnail=probe("synthetic/thumbnail.jpg", "E"),
            subtitles_es=probe("synthetic/subtitles-es.srt", "F"),
            provenance=probe("synthetic/provenance.json", "1"),
            review_checklist=probe("synthetic/review-checklist.json", "2"),
        ),
    )
    result = build_publication_package(request)

    assert result.status == PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE
    assert result.asset_count == 8
    assert result.required_asset_count == 8
    assert result.present_required_asset_count == 8
    assert result.hashed_required_asset_count == 8
    assert result.all_required_assets_present is True
    assert result.all_required_assets_hashed is True
    assert result.finalization_evidence_valid is True
    assert result.rights_ready is True
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
    assert all(asset.sha256 and len(asset.sha256) == 64 for asset in result.assets)
    assert all(
        not (asset.source_path or "").startswith(("D:\\", "E:\\"))
        for asset in result.assets
    )

    print("PUBLICATION_PACKAGE_CLOUD_DRY_RUN=PASS")
    print("PUBLICATION_PACKAGE_VERSION=publication-package-v0.2")
    print("CANONICAL_REVIEW_EVIDENCE=8_OF_8")
    print("CANONICAL_REQUIRED_ASSETS=8_OF_8")
    print("REQUIRED_ASSET_HASHES=8_OF_8")
    print("REAL_MEDIA_USED=FALSE")
    print("WRITES_FILES=FALSE")
    print("UPLOADS_FILES=FALSE")
    print("NETWORK_CALLS=0")
    print("WEBHOOK_CALLS=0")
    print("AUTO_PUBLICATION=FALSE")
    print("AUTHORIZATION_TO_PUBLISH=FALSE")
    print("MARKS_PUBLISHED=FALSE")
    print("LOCAL_FINAL_CERTIFICATION_REQUIRED=TRUE")


if __name__ == "__main__":
    main()
