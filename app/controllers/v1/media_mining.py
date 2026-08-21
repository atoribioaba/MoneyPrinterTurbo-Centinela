from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.media_mining import MediaMiningRequest
from app.services.media_mining import build_media_mining
from app.utils import utils

router = new_router()


@router.get("/media-mining/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "media-mining-v0.1",
            "planning_only": True,
            "candidate_tool": "PySceneDetect",
            "candidate_detector": "AdaptiveDetector",
            "scenedetect_invocations": 0,
            "auto_publication": False,
        },
    )


@router.post("/media-mining/plan")
def plan(body: MediaMiningRequest):
    try:
        result = build_media_mining(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
