from app.controllers.v1.base import new_router
from app.models.production_orchestrator import ProductionOrchestratorRequest
from app.services.production_orchestrator import build_production_orchestrator
from app.utils import utils

router = new_router()


@router.get("/production-orchestrator/health")
def health():
    return utils.get_response(200, {
        "status": "ok",
        "version": "production-orchestrator-v0.1",
        "reuses_existing_pipeline": True,
        "invokes_render": False,
        "auto_publication": False,
    })


@router.post("/production-orchestrator/plan")
def plan(body: ProductionOrchestratorRequest):
    return utils.get_response(200, build_production_orchestrator(body).model_dump(mode="json"))
