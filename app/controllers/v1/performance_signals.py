from app.controllers.v1.base import new_router
from app.models.performance_signals import PerformanceSignalsRequest
from app.services.performance_signals import build_performance_signals
from app.utils import utils

router = new_router()


@router.get("/performance-signals/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "performance-signals-v0.1",
            "planning_only": True,
            "cross_platform_ranking": False,
            "composite_score_enabled": False,
            "causal_claims": False,
        },
    )


@router.post("/performance-signals/plan")
def plan(body: PerformanceSignalsRequest):
    result = build_performance_signals(body)
    return utils.get_response(200, result.model_dump(mode="json"))
