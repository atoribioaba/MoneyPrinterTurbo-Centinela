from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.finalization_e2e import FinalizationE2EStatus
from app.models.publication_package import (
    PUBLICATION_PACKAGE_VERSION,
    PackageAsset,
    PublicationPackagePlan,
    PublicationPackageRequest,
    PublicationPackageStatus,
    PublicationSupportAssetProbe,
)


def _hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(payload).hexdigest().upper()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def _normalized_sha256(value: str | None) -> str | None:
    return value.upper() if value else None


def _support_asset(
    *,
    asset_id: str,
    target_filename: str,
    probe: PublicationSupportAssetProbe,
) -> PackageAsset:
    return PackageAsset(
        asset_id=asset_id,
        source_path=probe.source_path,
        target_filename=target_filename,
        present=probe.present,
        sha256=_normalized_sha256(probe.sha256),
    )


def _finalization_evidence_valid(request: PublicationPackageRequest) -> bool:
    finalization = request.finalization
    return bool(
        finalization.status == FinalizationE2EStatus.FINALIZATION_E2E_PASS
        and finalization.human_review_recorded
        and finalization.check_count > 0
        and finalization.failed_count == 0
        and finalization.passed_count == finalization.check_count
        and finalization.artifact_count >= 2
    )


def build_publication_package(
    request: PublicationPackageRequest,
) -> PublicationPackagePlan:
    finalization = request.finalization
    by_profile = {artifact.profile_id: artifact for artifact in finalization.artifacts}
    master = by_profile.get("MASTER_VERTICAL_2160X3840")
    social = by_profile.get("SOCIAL_VERTICAL_1080X1920")

    assets: list[PackageAsset] = []
    metadata_present = request.metadata is not None
    finalization_evidence_valid = _finalization_evidence_valid(request)

    if finalization.status == FinalizationE2EStatus.FINALIZATION_E2E_PASS:
        assets.extend(
            [
                PackageAsset(
                    asset_id="master",
                    source_path=master.file_path if master else None,
                    target_filename="master_2160x3840.mp4",
                    present=bool(master and master.exists),
                    sha256=_normalized_sha256(master.sha256 if master else None),
                    publication_rights_ready=bool(
                        master and master.publication_rights_ready
                    ),
                ),
                PackageAsset(
                    asset_id="social",
                    source_path=social.file_path if social else None,
                    target_filename="social_1080x1920.mp4",
                    present=bool(social and social.exists),
                    sha256=_normalized_sha256(social.sha256 if social else None),
                    publication_rights_ready=bool(
                        social and social.publication_rights_ready
                    ),
                ),
                _support_asset(
                    asset_id="thumbnail",
                    target_filename="thumbnail.jpg",
                    probe=request.support.thumbnail,
                ),
                _support_asset(
                    asset_id="subtitles_es",
                    target_filename="subtitles-es.srt",
                    probe=request.support.subtitles_es,
                ),
                _support_asset(
                    asset_id="provenance",
                    target_filename="sources-licenses-provenance.json",
                    probe=request.support.provenance,
                ),
                _support_asset(
                    asset_id="publication_checklist",
                    target_filename="publication-checklist.json",
                    probe=request.support.review_checklist,
                ),
            ]
        )

        if request.metadata is not None:
            metadata_payload = json.dumps(
                request.metadata.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            assets.extend(
                [
                    PackageAsset(
                        asset_id="caption",
                        target_filename="caption.txt",
                        present=True,
                        sha256=_hash_text(request.metadata.caption),
                        generated_from_metadata=True,
                    ),
                    PackageAsset(
                        asset_id="metadata",
                        target_filename="metadata.json",
                        present=True,
                        sha256=_hash_text(metadata_payload),
                        generated_from_metadata=True,
                    ),
                ]
            )

    required = [asset for asset in assets if asset.required]
    present_required = [asset for asset in required if asset.present]
    hashed_required = [asset for asset in required if asset.sha256 is not None]
    rights_ready = bool(
        master
        and social
        and master.publication_rights_ready
        and social.publication_rights_ready
        and request.support.provenance.present
        and request.support.provenance.sha256
    )
    all_required_assets_present = bool(required) and len(present_required) == len(required)
    all_required_assets_hashed = bool(required) and len(hashed_required) == len(required)

    if finalization.status != FinalizationE2EStatus.FINALIZATION_E2E_PASS:
        status = PublicationPackageStatus.WAITING_FOR_FINALIZATION
    elif not finalization_evidence_valid:
        status = PublicationPackageStatus.WAITING_FOR_FINALIZATION
    elif request.metadata is None:
        status = PublicationPackageStatus.WAITING_FOR_METADATA
    elif not (
        len(required) == 8
        and all_required_assets_present
        and all_required_assets_hashed
        and rights_ready
    ):
        status = PublicationPackageStatus.WAITING_FOR_REQUIRED_ASSETS
    else:
        status = PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE

    stable = {
        "version": PUBLICATION_PACKAGE_VERSION,
        "finalization": finalization.finalization_e2e_hash,
        "metadata": (
            request.metadata.model_dump(mode="json") if request.metadata else None
        ),
        "support": request.support.model_dump(mode="json"),
        "assets": [asset.model_dump(mode="json") for asset in assets],
        "finalization_evidence_valid": finalization_evidence_valid,
        "rights_ready": rights_ready,
        "status": status.value,
    }

    return PublicationPackagePlan(
        source_finalization_e2e_hash=finalization.finalization_e2e_hash,
        status=status,
        asset_count=len(assets),
        required_asset_count=len(required),
        present_required_asset_count=len(present_required),
        hashed_required_asset_count=len(hashed_required),
        assets=assets,
        metadata_present=metadata_present,
        human_review_recorded=finalization.human_review_recorded,
        finalization_evidence_valid=finalization_evidence_valid,
        rights_ready=rights_ready,
        all_required_assets_present=all_required_assets_present,
        all_required_assets_hashed=all_required_assets_hashed,
        publication_package_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
