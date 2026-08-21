from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.audio_mastering import AudioMasteringRequest
from app.services.audio_mastering import build_audio_mastering
from app.utils import utils

router = new_router()


@router.get("/audio-mastering/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "audio-mastering-v0.1",
            "planning_only": True,
            "normalization_method": "FFMPEG_LOUDNORM_TWO_PASS_WHEN_INPUT_AVAILABLE",
            "gpu_required": False,
            "auto_publication": False,
        },
    )


@router.post("/audio-mastering/plan")
def plan(body: AudioMasteringRequest):
    try:
        result = build_audio_mastering(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
