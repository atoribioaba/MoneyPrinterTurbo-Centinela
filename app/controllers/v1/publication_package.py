from app.controllers.v1.base import new_router
from app.models.publication_package import (
    PUBLICATION_PACKAGE_VERSION,
    PublicationPackageRequest,
)
from app.services.publication_package import build_publication_package
from app.utils import utils

router = new_router()


@router.get("/publication-package/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": PUBLICATION_PACKAGE_VERSION,
            "planning_only": True,
            "manual_publication_only": True,
            "writes_files": False,
            "uploads_files": False,
            "network_calls": 0,
            "webhook_calls": 0,
            "auto_publication": False,
            "authorization_to_publish": False,
            "marks_published": False,
            "local_final_certification_required": True,
        },
    )


@router.post("/publication-package/plan")
def plan(body: PublicationPackageRequest):
    return utils.get_response(
        200,
        build_publication_package(body).model_dump(mode="json"),
    )
