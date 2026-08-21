from __future__ import annotations

from app.controllers.v1.base import new_router
from app.services.wangp_backend import WanGPBackendAuditor
from app.utils import utils


router = new_router()
auditor = WanGPBackendAuditor()


@router.get("/wangp-backend/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": auditor.version,
            "audit_only": True,
            "default_path": r"E:\IA\WanGP",
            "imports_wangp_runtime": False,
            "launches_wangp": False,
            "network_access_used": False,
            "downloads_models": False,
            "modifies_wangp": False,
            "large_download_authorized": False,
        },
    )


@router.get("/wangp-backend/audit")
def audit(path: str = r"E:\IA\WanGP"):
    result = auditor.audit(path)
    return utils.get_response(
        200,
        result.model_dump(mode="json"),
    )
