from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.rollback_decision_gate import RollbackDecisionRequest
from app.services.rollback_decision_gate import build_rollback_decision_plan
from app.utils import utils

router = new_router()


@router.get("/rollback-decision-gate/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "rollback-decision-gate-v0.1",
            "decision_automatic": True,
            "executes_rollback": False,
            "writes_runtime_config": False,
            "activates_policy": False,
        },
    )


@router.post("/rollback-decision-gate/plan")
def plan(body: RollbackDecisionRequest):
    try:
        result = build_rollback_decision_plan(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
