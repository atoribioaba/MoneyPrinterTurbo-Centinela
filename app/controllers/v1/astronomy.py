from fastapi import HTTPException

from app.controllers.v1.base import (
    new_router,
)
from app.models.astronomy import (
    AstronomyContextRequest,
    AstronomyContextResponse,
    AstronomyHealthResponse,
)
from app.services.astronomy_core import (
    AstronomyCoreError,
    build_astronomy_context,
    get_astronomy_health,
)
from app.utils import utils


router = new_router()


@router.get(
    "/astronomy/health",
    response_model=AstronomyHealthResponse,
    summary=(
        "Astronomy core health "
        "and engine information"
    ),
)
def astronomy_health():
    health = get_astronomy_health()

    return utils.get_response(
        200,
        health.model_dump(
            mode="json"
        ),
    )


@router.post(
    "/astronomy/context",
    response_model=AstronomyContextResponse,
    summary=(
        "Build deterministic "
        "astronomy context"
    ),
)
def astronomy_context(
    body: AstronomyContextRequest,
):
    try:
        context = build_astronomy_context(
            body
        )

    except AstronomyCoreError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return utils.get_response(
        200,
        context.model_dump(
            mode="json"
        ),
    )
