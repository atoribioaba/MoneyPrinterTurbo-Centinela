from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from typing import Any
from app.models.finalization_e2e import FinalizationE2EStatus
from app.models.publication_package import *
def _hash(v:Any)->str: return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest().upper()
def build_publication_package(request:PublicationPackageRequest)->PublicationPackagePlan:
    assets=[]
    if request.finalization.status != FinalizationE2EStatus.FINALIZATION_E2E_PASS:
        status=PublicationPackageStatus.WAITING_FOR_FINALIZATION
    elif request.metadata is None:
        status=PublicationPackageStatus.WAITING_FOR_METADATA
    else:
        by_profile={a.profile_id:a for a in request.finalization.artifacts}
        master=by_profile.get("MASTER_VERTICAL_2160X3840"); social=by_profile.get("SOCIAL_VERTICAL_1080X1920")
        assets=[
            PackageAsset(asset_id="master",source_path=master.file_path if master else None,target_filename="master_2160x3840.mp4",present=bool(master and master.exists)),
            PackageAsset(asset_id="social",source_path=social.file_path if social else None,target_filename="social_1080x1920.mp4",present=bool(social and social.exists)),
            PackageAsset(asset_id="caption",target_filename="caption.txt",present=True),
            PackageAsset(asset_id="metadata",target_filename="metadata.json",present=True),
            PackageAsset(asset_id="publication_checklist",target_filename="publication-checklist.json",present=True),
        ]
        status=PublicationPackageStatus.READY_FOR_MANUAL_PACKAGE
    stable={"version":PUBLICATION_PACKAGE_VERSION,"finalization":request.finalization.finalization_e2e_hash,"metadata":request.metadata.model_dump(mode="json") if request.metadata else None,"assets":[a.model_dump(mode="json") for a in assets],"status":status.value}
    return PublicationPackagePlan(source_finalization_e2e_hash=request.finalization.finalization_e2e_hash,status=status,asset_count=len(assets),assets=assets,metadata_present=request.metadata is not None,publication_package_hash=_hash(stable),generated_at_utc=datetime.now(timezone.utc))
