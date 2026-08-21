from __future__ import annotations

from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.smart_ken_burns import SmartKenBurnsRequest
from app.services.smart_ken_burns import (
    SmartKenBurnsError,
    SmartKenBurnsPlanner,
)
from app.utils import utils


router = new_router()
planner = SmartKenBurnsPlanner()


@router.get("/smart-ken-burns/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": planner.version,
            "ken_burns_phase": True,
            "deterministic": True,
            "normalized_geometry": True,
            "image_only_motion": True,
            "motion_mapping": {
                "OBSERVE_LOCKED": "HOLD",
                "NATURAL_MOTION_ONLY": "HOLD",
                "VERY_SLOW_PUSH": "PUSH_IN",
                "CONTROLLED_REVEAL": "CONTROLLED_REVEAL",
                "GENTLE_PULL_BACK": "PULL_BACK",
            },
            "uses_llm": False,
            "gpu_required": False,
            "renders_video": False,
            "searches_material": False,
            "changes_material_identity": False,
            "changes_fit_mode": False,
            "tracking_reexecuted": False,
            "smartfocal_reexecuted": False,
            "reframing_reexecuted": False,
            "auto_publication": False,
        },
    )


@router.post("/smart-ken-burns/plan")
def plan_ken_burns(body: SmartKenBurnsRequest):
    try:
        result = planner.build(body)
    except SmartKenBurnsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return utils.get_response(
        200,
        result.model_dump(mode="json"),
    )
