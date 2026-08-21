from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.sound_design import SoundDesignRequest
from app.services.sound_design import build_sound_design
from app.utils import utils

router = new_router()

@router.get("/sound-design/health")
def health():
    return utils.get_response(200, {
        "status": "ok",
        "version": "sound-design-v0.1",
        "planning_only": True,
        "uses_llm": False,
        "gpu_required": False,
        "auto_publication": False,
    })

@router.post("/sound-design/plan")
def plan(body: SoundDesignRequest):
    try:
        result = build_sound_design(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
