from app.controllers.v1.base import new_router
from app.models.retention_intelligence import RetentionIntelligenceRequest
from app.services.retention_intelligence import build_retention_intelligence
from app.utils import utils

router = new_router()


@router.get("/retention-intelligence/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "retention-intelligence-v0.1",
            "planning_only": True,
            "interpolates_missing_points": False,
            "causal_claims": False,
            "recommendations_generated": False,
        },
    )


@router.post("/retention-intelligence/plan")
def plan(body: RetentionIntelligenceRequest):
    result = build_retention_intelligence(body)
    return utils.get_response(200, result.model_dump(mode="json"))
