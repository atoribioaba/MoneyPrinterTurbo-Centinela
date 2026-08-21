from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.transition_director import TransitionDirectorRequest
from app.services.transition_director import build_transition_director
from app.utils import utils

router = new_router()

@router.get("/transition-director/health")
def health():
    return utils.get_response(200, {
        "status": "ok",
        "version": "transition-director-v0.1",
        "planning_only": True,
        "uses_llm": False,
        "gpu_required": False,
        "auto_publication": False,
    })

@router.post("/transition-director/plan")
def plan(body: TransitionDirectorRequest):
    try:
        result = build_transition_director(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
