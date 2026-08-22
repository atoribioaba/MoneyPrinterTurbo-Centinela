from app.controllers.v1.base import new_router
from app.models.evidence_recommendation_gate import (
    EvidenceRecommendationGateRequest,
)
from app.services.evidence_recommendation_gate import (
    build_evidence_recommendation_gate,
)
from app.utils import utils

router = new_router()


@router.get("/evidence-recommendation-gate/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "evidence-recommendation-gate-v0.1",
            "planning_only": True,
            "association_only_recommendations": False,
            "updates_director_policy": False,
            "auto_apply": False,
            "auto_publication": False,
        },
    )


@router.post("/evidence-recommendation-gate/plan")
def plan(body: EvidenceRecommendationGateRequest):
    result = build_evidence_recommendation_gate(body)
    return utils.get_response(200, result.model_dump(mode="json"))
