from __future__ import annotations

from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.visual_story_graph import VisualStoryGraphRequest
from app.services.visual_story_graph import (
    VisualStoryGraphBuilder,
    VisualStoryGraphError,
)
from app.utils import utils


router = new_router()
builder = VisualStoryGraphBuilder()


@router.get("/visual-story-graph/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": builder.version,
            "deterministic": True,
            "planning_only": True,
            "graph_model": "directed_sequential_with_subject_threads",
            "uses_llm": False,
            "gpu_required": False,
            "renders_video": False,
            "searches_material": False,
            "quality_scoring_triggered": False,
            "tracking_triggered": False,
            "smartfocal_triggered": False,
            "wangp_triggered": False,
            "auto_publication": False,
        },
    )


@router.post("/visual-story-graph/plan")
def build_visual_story_graph(body: VisualStoryGraphRequest):
    try:
        result = builder.build(body)
    except VisualStoryGraphError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return utils.get_response(
        200,
        result.model_dump(mode="json"),
    )
