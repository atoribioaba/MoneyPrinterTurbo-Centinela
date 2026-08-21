from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.delivery_render import DeliveryRenderRequest
from app.services.delivery_render import build_delivery_render
from app.utils import utils

router = new_router()


@router.get("/delivery-render/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "delivery-render-v0.1",
            "planning_only": True,
            "master": "2160x3840@30",
            "social": "1080x1920@30",
            "source_strategy": "ORIGINAL_SOURCE_RERENDER",
            "renders_project_video": False,
            "auto_publication": False,
        },
    )


@router.post("/delivery-render/plan")
def plan(body: DeliveryRenderRequest):
    try:
        result = build_delivery_render(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
