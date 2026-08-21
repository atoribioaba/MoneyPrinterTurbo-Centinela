from __future__ import annotations

import shutil

from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.best_moment import BestMomentRequest
from app.services.best_moment import BestMomentDetector, BestMomentError
from app.utils import utils


router = new_router()
detector = BestMomentDetector()


@router.get("/best-moment/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": detector.version,
            "deterministic": True,
            "candidate_policy": "EQUALLY_SPACED_WINDOW_CENTERS_V01",
            "scoring_profile": "TEMPORAL_TECHNICAL_V01",
            "ffmpeg_binary": shutil.which("ffmpeg"),
            "uses_llm": False,
            "gpu_required": False,
            "renders_video": False,
            "searches_material": False,
            "changes_material_identity": False,
            "tracking_triggered": False,
            "smartfocal_triggered": False,
            "auto_publication": False,
        },
    )


@router.post("/best-moment/detect")
def detect_best_moment(body: BestMomentRequest):
    try:
        result = detector.build(body)
    except BestMomentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return utils.get_response(
        200,
        result.model_dump(mode="json"),
    )
