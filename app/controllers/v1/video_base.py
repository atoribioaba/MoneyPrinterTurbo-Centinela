from __future__ import annotations

from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.video_base import VideoBasePlanRequest, VideoBaseRenderRequest
from app.services.video_base_planner import (
    VideoBasePlanBlockedError,
    VideoBasePlanError,
    VideoBasePlanner,
)
from app.services.video_base_renderer import FFmpegSceneRenderer, VideoBaseRenderError
from app.utils import utils


router = new_router()


def _planner():
    # Lazy construction avoids filesystem/database side effects during health imports.
    return VideoBasePlanner()


@router.get("/video-base/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "video-base-v0.1",
            "resolution": "1080x1920",
            "fps": 30,
            "audio": False,
            "material_selection_authority": "MaterialSelectionPlan",
            "material_search_triggered": False,
            "smartfocal_auto_triggered": False,
            "semantic_matcher_triggered": False,
            "wangp_triggered": False,
            "auto_publication": False,
        },
    )


@router.post("/video-base/plan")
def plan_video_base(body: VideoBasePlanRequest):
    try:
        result = _planner().build(body)
    except (VideoBasePlanBlockedError, VideoBasePlanError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))


@router.post("/video-base/render")
def render_video_base(body: VideoBaseRenderRequest):
    try:
        planned = _planner().build(body)
        result = FFmpegSceneRenderer().render(
            planned,
            keep_segments=body.keep_segments,
        )
    except (VideoBasePlanBlockedError, VideoBasePlanError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VideoBaseRenderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
