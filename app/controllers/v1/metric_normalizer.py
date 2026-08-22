from app.controllers.v1.base import new_router
from app.models.metric_normalizer import MetricNormalizerRequest
from app.services.metric_normalizer import build_metric_normalizer
from app.utils import utils

router = new_router()


@router.get("/metric-normalizer/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "metric-normalizer-v0.1",
            "planning_only": True,
            "cross_platform_equivalence_assumed": False,
            "api_calls": 0,
            "auto_publication": False,
        },
    )


@router.post("/metric-normalizer/plan")
def plan(body: MetricNormalizerRequest):
    result = build_metric_normalizer(body)
    return utils.get_response(200, result.model_dump(mode="json"))
