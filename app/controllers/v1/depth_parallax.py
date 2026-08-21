from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.depth_parallax import DepthParallaxRequest
from app.services.depth_parallax import build_depth_parallax
from app.utils import utils

router = new_router()

@router.get("/depth-parallax/health")
def health():
    return utils.get_response(200, {
        "status": "ok",
        "version": "depth-parallax-v0.1",
        "planning_only": True,
        "uses_llm": False,
        "gpu_required": False,
        "auto_publication": False,
    })

@router.post("/depth-parallax/plan")
def plan(body: DepthParallaxRequest):
    try:
        result = build_depth_parallax(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
