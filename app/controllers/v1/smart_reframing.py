from __future__ import annotations

from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.smart_reframing import SmartReframingRequest
from app.services.smart_reframing import (
    SmartReframingError,
    SmartReframingPlanner,
)
from app.utils import utils


router = new_router()
planner = SmartReframingPlanner()


@router.get("/smart-reframing/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": planner.version,
            "reframing_phase": True,
            "deterministic": True,
            "target": "1080x1920",
            "smartfocal_foundation_reused": True,
            "smartfocal_fallback_contract_used": True,
            "precedence": "F11_TRACKING__SMARTFOCAL__F6_FOCAL",
            "dynamic_tracking": True,
            "uses_llm": False,
            "gpu_required": False,
            "renders_video": False,
            "searches_material": False,
            "changes_material_identity": False,
            "changes_fit_mode": False,
            "best_moment_search_triggered": False,
            "tracking_reexecuted": False,
            "smartfocal_analyzer_invocations": 0,
            "auto_publication": False,
        },
    )


@router.post("/smart-reframing/plan")
def plan_reframing(body: SmartReframingRequest):
    try:
        result = planner.build(body)
    except SmartReframingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return utils.get_response(
        200,
        result.model_dump(mode="json"),
    )
