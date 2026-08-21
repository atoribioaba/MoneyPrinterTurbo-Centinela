from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.quality_gates import QualityGatesRequest
from app.services.quality_gates import build_quality_gates
from app.utils import utils

router = new_router()


@router.get("/quality-gates/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "quality-gates-v0.1",
            "planning_only": True,
            "human_approval_required": True,
            "auto_publication": False,
        },
    )


@router.post("/quality-gates/plan")
def plan(body: QualityGatesRequest):
    try:
        result = build_quality_gates(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
