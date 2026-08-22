from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.controlled_promotion_gate import ControlledPromotionRequest
from app.services.controlled_promotion_gate import build_controlled_promotion_plan
from app.utils import utils

router = new_router()


@router.get("/controlled-promotion-gate/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "controlled-promotion-gate-v0.1",
            "requires_human_promotion_decision": True,
            "activates_policy": False,
            "writes_runtime_config": False,
            "auto_apply": False,
        },
    )


@router.post("/controlled-promotion-gate/plan")
def plan(body: ControlledPromotionRequest):
    try:
        result = build_controlled_promotion_plan(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
