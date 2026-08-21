from __future__ import annotations

from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.astronomy_director import AstronomyVideoPlan
from app.models.visual_story_graph import VisualStoryGraph
from app.services.astronomy_motion_graphics import (
    AstronomyMotionGraphicsError,
    build_motion_graphics,
)
from app.utils import utils


router = new_router()


@router.get("/astronomy-motion-graphics/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "astronomy-motion-graphics-v0.1",
            "planning_only": True,
            "explicit_objects_only": True,
            "plan_claims_only": True,
            "verified_claim_fact_ids_preserved": True,
            "invented_coordinates": False,
            "invented_trajectories": False,
            "invented_numeric_values": False,
            "uses_llm": False,
            "gpu_required": False,
            "renders_graphics": False,
            "auto_publication": False,
        },
    )


@router.post("/astronomy-motion-graphics/plan")
def plan_motion_graphics(
    plan: AstronomyVideoPlan,
    graph: VisualStoryGraph,
):
    try:
        result = build_motion_graphics(plan, graph)
    except AstronomyMotionGraphicsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return utils.get_response(
        200,
        result.model_dump(mode="json"),
    )
