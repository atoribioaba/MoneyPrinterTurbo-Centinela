from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.shadow_policy_evaluator import ShadowPolicyRequest
from app.services.shadow_policy_evaluator import build_shadow_policy_plan
from app.utils import utils

router = new_router()


@router.get("/shadow-policy-evaluator/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "shadow-policy-evaluator-v0.1",
            "shadow_only": True,
            "runtime_effect": False,
            "writes_runtime_config": False,
            "activates_policy": False,
        },
    )


@router.post("/shadow-policy-evaluator/plan")
def plan(body: ShadowPolicyRequest):
    try:
        result = build_shadow_policy_plan(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
