from __future__ import annotations

from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.cinematic_director import CinematicDirectorRequest
from app.services.cinematic_director import CinematicDirector, CinematicDirectorError
from app.utils import utils


router = new_router()
director = CinematicDirector()


@router.get("/cinematic-director/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": director.version,
            "deterministic": True,
            "planning_only": True,
            "uses_llm": False,
            "gpu_required": False,
            "renders_video": False,
            "searches_material": False,
            "smartfocal_triggered": False,
            "semantic_matcher_triggered": False,
            "wangp_triggered": False,
            "tts_triggered": False,
            "whisper_triggered": False,
            "auto_publication": False,
        },
    )


@router.post("/cinematic-director/plan")
def plan_cinematic_direction(body: CinematicDirectorRequest):
    try:
        result = director.build(body)
    except CinematicDirectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return utils.get_response(
        200,
        result.model_dump(mode="json"),
    )
