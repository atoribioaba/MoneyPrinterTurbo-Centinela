from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.astronomy_director import (
    AstronomyDirectorHealthResponse,
    AstronomyDirectorPlanResponse,
    AstronomyDirectorRequest,
)
from app.services.astronomy_director import (
    AstronomyDirectorError,
    generate_astronomy_video_plan,
    get_director_health,
)
from app.utils import utils

router = new_router()


@router.get(
    "/astronomy/director/health",
    response_model=AstronomyDirectorHealthResponse,
    summary="Astronomy Director local LLM health",
)
def astronomy_director_health():
    health = get_director_health()
    return utils.get_response(200, health.model_dump(mode="json"))


@router.post(
    "/astronomy/director/plan",
    response_model=AstronomyDirectorPlanResponse,
    summary="Generate grounded AstronomyVideoPlan",
)
def astronomy_director_plan(body: AstronomyDirectorRequest):
    try:
        plan = generate_astronomy_video_plan(body)
    except AstronomyDirectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, plan.model_dump(mode="json"))
