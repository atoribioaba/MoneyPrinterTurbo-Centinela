from __future__ import annotations

from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.master_image_i2v import MasterImageI2VRequest
from app.services.master_image_i2v import (
    MasterImageI2VError,
    MasterImageI2VPlanner,
)
from app.utils import utils


router = new_router()
planner = MasterImageI2VPlanner()


@router.get("/master-image-i2v/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": planner.version,
            "planning_only": True,
            "requires_f15_backend": True,
            "target_backend_family": "WanGP",
            "backend_contract": "WANGP_API_OR_HEADLESS_RESOLVED_IN_F15",
            "explicit_ai_approval_required": True,
            "image_only_generation": True,
            "output_visual_origin": "AI_GENERATED",
            "output_scientific_status": "RECREACION_VISUAL",
            "ken_burns_is_fallback": True,
            "motion_stacking": False,
            "uses_llm": False,
            "gpu_required": False,
            "renders_video": False,
            "downloads_models": False,
            "wangp_invocations": 0,
            "auto_publication": False,
        },
    )


@router.post("/master-image-i2v/plan")
def plan_master_image_i2v(body: MasterImageI2VRequest):
    try:
        result = planner.build(body)
    except MasterImageI2VError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return utils.get_response(
        200,
        result.model_dump(mode="json"),
    )
