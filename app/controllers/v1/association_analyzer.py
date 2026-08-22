from app.controllers.v1.base import new_router
from app.models.association_analyzer import AssociationAnalyzerRequest
from app.services.association_analyzer import build_association_analyzer
from app.utils import utils

router = new_router()


@router.get("/association-analyzer/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "association-analyzer-v0.1",
            "planning_only": True,
            "method": "SPEARMAN_RANK_CORRELATION",
            "cross_platform_pooling": False,
            "p_values_calculated": False,
            "causal_claims": False,
        },
    )


@router.post("/association-analyzer/plan")
def plan(body: AssociationAnalyzerRequest):
    result = build_association_analyzer(body)
    return utils.get_response(200, result.model_dump(mode="json"))
