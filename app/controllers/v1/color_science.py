from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.color_science import ColorScienceRequest
from app.services.color_science import build_color_science
from app.utils import utils

router = new_router()

@router.get("/color-science/health")
def health():
    return utils.get_response(200, {
        "status": "ok",
        "version": "color-science-v0.1",
        "planning_only": True,
        "uses_llm": False,
        "gpu_required": False,
        "auto_publication": False,
    })

@router.post("/color-science/plan")
def plan(body: ColorScienceRequest):
    try:
        result = build_color_science(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
