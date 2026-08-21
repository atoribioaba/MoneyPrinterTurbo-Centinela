from __future__ import annotations

from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.astronomical_tracker import AstronomicalTrackingRequest
from app.services.astronomical_tracker import (
    AstronomicalObjectTracker,
    AstronomicalTrackingError,
)
from app.utils import utils


router = new_router()
tracker = AstronomicalObjectTracker()


@router.get("/astronomical-tracker/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": tracker.version,
            "tracking_phase": True,
            "deterministic": True,
            "backend_policy": "EXPLICIT_SEED_SINGLE_OBJECT_TRACKING_V01",
            "default_backend": "opencv_csrt",
            "opencv_loaded_lazily": True,
            "dependency_mutation": False,
            "uses_llm": False,
            "gpu_required": False,
            "renders_video": False,
            "searches_material": False,
            "changes_material_identity": False,
            "best_moment_search_triggered": False,
            "smartfocal_triggered": False,
            "reframing_triggered": False,
            "auto_publication": False,
        },
    )


@router.post("/astronomical-tracker/track")
def track_astronomical_object(body: AstronomicalTrackingRequest):
    try:
        result = AstronomicalObjectTracker().build(body)
    except AstronomicalTrackingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return utils.get_response(
        200,
        result.model_dump(mode="json"),
    )
