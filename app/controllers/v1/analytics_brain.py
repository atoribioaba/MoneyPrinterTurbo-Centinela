from app.controllers.v1.base import new_router
from app.models.analytics_brain import AnalyticsBrainRequest
from app.services.analytics_brain import build_analytics_brain
from app.utils import utils

router = new_router()


@router.get("/analytics-brain/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "analytics-brain-v0.1",
            "planning_only": True,
            "storage_candidate": "SQLite",
            "storage_writes": 0,
            "api_calls": 0,
            "auto_publication": False,
        },
    )


@router.post("/analytics-brain/plan")
def plan(body: AnalyticsBrainRequest):
    result = build_analytics_brain(body)
    return utils.get_response(200, result.model_dump(mode="json"))
