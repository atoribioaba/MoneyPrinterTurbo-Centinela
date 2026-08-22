from app.controllers.v1.base import new_router
from app.models.canary_policy_planner import CanaryPolicyRequest
from app.services.canary_policy_planner import build_canary_policy_plan
from app.utils import utils

router = new_router()


@router.get("/canary-policy-planner/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "canary-policy-planner-v0.1",
            "max_exposure_fraction": 0.10,
            "executes_canary": False,
            "requires_human_launch": True,
            "activates_policy": False,
        },
    )


@router.post("/canary-policy-planner/plan")
def plan(body: CanaryPolicyRequest):
    return utils.get_response(200, build_canary_policy_plan(body).model_dump(mode="json"))
