from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.quality_comparator import QualityComparatorRequest
from app.services.quality_comparator import build_quality_comparator
from app.utils import utils

router = new_router()


@router.get("/quality-comparator/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "quality-comparator-v0.1",
            "planning_only": True,
            "executes_ab_comparison": False,
            "selects_winner": False,
            "auto_publication": False,
        },
    )


@router.post("/quality-comparator/plan")
def plan(body: QualityComparatorRequest):
    try:
        result = build_quality_comparator(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
