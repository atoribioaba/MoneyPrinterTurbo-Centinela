from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.subtitle_intelligence import SubtitleIntelligenceRequest
from app.services.subtitle_intelligence import build_subtitle_intelligence
from app.utils import utils

router = new_router()


@router.get("/subtitle-intelligence/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "subtitle-intelligence-v0.1",
            "planning_only": True,
            "timestamp_priority": "NATIVE_TTS_BOUNDARIES_FIRST",
            "fallback_candidate": "faster-whisper",
            "whisper_triggered": False,
            "auto_publication": False,
        },
    )


@router.post("/subtitle-intelligence/plan")
def plan(body: SubtitleIntelligenceRequest):
    try:
        result = build_subtitle_intelligence(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
