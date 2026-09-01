from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.material_selection import MaterialSelectionRequest
from app.services.material_selection import MaterialSelectionError, MaterialSelector
from app.utils import utils


router = new_router()

_selector: MaterialSelector | None = None


def get_selector() -> MaterialSelector:
    global _selector

    if _selector is None:
        _selector = MaterialSelector()

    return _selector


@router.get("/material-selection/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "selector_version": "material-selection-v0.1",
            "deterministic": True,
            "semantic_model_required": False,
            "provider_download_triggered": False,
            "auto_publication": False,
        },
    )


@router.post("/material-selection/plan")
def select_materials(
    body: MaterialSelectionRequest,
):
    selector = get_selector()

    try:
        result = selector.select_plan(body)

    except MaterialSelectionError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return utils.get_response(
        200,
        result.model_dump(mode="json"),
    )
