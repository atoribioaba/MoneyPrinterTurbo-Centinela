from app.controllers.v1.base import new_router
from app.models.outcome_linker import OutcomeLinkerRequest
from app.services.outcome_linker import build_outcome_linker
from app.utils import utils

router = new_router()


@router.get("/outcome-linker/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "outcome-linker-v0.1",
            "planning_only": True,
            "joins_native_only_metrics": False,
            "cross_platform_join": False,
            "database_writes": 0,
        },
    )


@router.post("/outcome-linker/plan")
def plan(body: OutcomeLinkerRequest):
    result = build_outcome_linker(body)
    return utils.get_response(200, result.model_dump(mode="json"))
