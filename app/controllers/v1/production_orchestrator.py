from app.controllers.v1.base import new_router
from app.models.production_orchestrator import (
    PRODUCTION_ORCHESTRATOR_VERSION,
    ProductionOrchestratorRequest,
)
from app.services.production_orchestrator import build_production_orchestrator
from app.utils import utils

router = new_router()


@router.get("/production-orchestrator/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": PRODUCTION_ORCHESTRATOR_VERSION,
            "reuses_existing_pipeline": True,
            "invokes_render": False,
            "invokes_network": False,
            "auto_publication": False,
            "authorization_to_publish": False,
            "marks_published": False,
            "human_approval_authority": "FinalizationE2E",
            "publication_package_authority": "PublicationPackage",
            "downstream_completion_declarative": False,
        },
    )


@router.post("/production-orchestrator/plan")
def plan(body: ProductionOrchestratorRequest):
    return utils.get_response(
        200,
        build_production_orchestrator(body).model_dump(mode="json"),
    )
