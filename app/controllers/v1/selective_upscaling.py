from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.selective_upscaling import SelectiveUpscalingRequest
from app.services.selective_upscaling import build_selective_upscaling
from app.utils import utils

router = new_router()


@router.get("/selective-upscaling/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "selective-upscaling-v0.1",
            "planning_only": True,
            "candidate_engine": "Real-ESRGAN-ncnn-vulkan",
            "runs_upscaler": False,
            "downloads_models": False,
            "auto_publication": False,
        },
    )


@router.post("/selective-upscaling/plan")
def plan(body: SelectiveUpscalingRequest):
    try:
        result = build_selective_upscaling(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
