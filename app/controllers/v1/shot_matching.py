from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.shot_matching import ShotMatchingRequest
from app.services.shot_matching import build_shot_matching
from app.utils import utils

router = new_router()

@router.get("/shot-matching/health")
def health():
    return utils.get_response(200, {
        "status": "ok",
        "version": "shot-matching-v0.1",
        "planning_only": True,
        "uses_llm": False,
        "gpu_required": False,
        "auto_publication": False,
    })

@router.post("/shot-matching/plan")
def plan(body: ShotMatchingRequest):
    try:
        result = build_shot_matching(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
