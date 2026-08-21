from __future__ import annotations

import shutil

from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.shot_quality import ShotQualityRequest
from app.services.shot_quality import ShotQualityError, ShotQualityScorer
from app.utils import utils


router = new_router()
scorer = ShotQualityScorer()


@router.get("/shot-quality/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": scorer.version,
            "deterministic": True,
            "technical_heuristic": True,
            "representative_frame_policy": "F6_SOURCE_START_SINGLE_FRAME",
            "ffmpeg_binary": shutil.which("ffmpeg"),
            "uses_llm": False,
            "gpu_required": False,
            "renders_video": False,
            "searches_material": False,
            "best_moment_search_triggered": False,
            "tracking_triggered": False,
            "smartfocal_triggered": False,
            "auto_publication": False,
        },
    )


@router.post("/shot-quality/score")
def score_shots(body: ShotQualityRequest):
    try:
        result = scorer.build(body)
    except ShotQualityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return utils.get_response(
        200,
        result.model_dump(mode="json"),
    )
