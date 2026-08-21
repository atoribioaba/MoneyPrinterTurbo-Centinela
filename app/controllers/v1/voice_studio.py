from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.voice_studio import VoiceStudioRequest
from app.services.voice_studio import build_voice_studio
from app.utils import utils

router = new_router()


@router.get("/voice-studio/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "voice-studio-v0.1",
            "planning_only": True,
            "uses_llm": False,
            "gpu_required": False,
            "auto_publication": False,
            "timestamp_policy": "TTS_NATIVE_BOUNDARIES_FIRST",
        },
    )


@router.post("/voice-studio/plan")
def plan(body: VoiceStudioRequest):
    try:
        result = build_voice_studio(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
