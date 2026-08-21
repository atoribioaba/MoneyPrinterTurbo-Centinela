from __future__ import annotations

from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.astronomy_director import AstronomyVideoPlan
from app.models.astronomy_motion_graphics import AstronomyMotionGraphicsPlan
from app.services.cinematic_infographics import (
    CinematicInfographicsError,
    build_cinematic_infographics,
)
from app.utils import utils


router = new_router()


@router.get("/cinematic-infographics/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "cinematic-infographics-v0.1",
            "planning_only": True,
            "plan_claims_only": True,
            "fact_ids_preserved": True,
            "scientific_status_preserved": True,
            "external_data_added": False,
            "invented_numbers": False,
            "invented_charts": False,
            "uses_llm": False,
            "gpu_required": False,
            "renders_infographics": False,
            "auto_publication": False,
        },
    )


@router.post("/cinematic-infographics/plan")
def plan_infographics(
    plan: AstronomyVideoPlan,
    graphics: AstronomyMotionGraphicsPlan,
):
    try:
        result = build_cinematic_infographics(plan, graphics)
    except CinematicInfographicsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return utils.get_response(
        200,
        result.model_dump(mode="json"),
    )
