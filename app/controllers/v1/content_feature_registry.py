from fastapi import HTTPException

from app.controllers.v1.base import new_router
from app.models.content_feature_registry import ContentFeatureRegistryRequest
from app.services.content_feature_registry import build_content_feature_registry
from app.utils import utils

router = new_router()


@router.get("/content-feature-registry/health")
def health():
    return utils.get_response(
        200,
        {
            "status": "ok",
            "version": "content-feature-registry-v0.1",
            "planning_only": True,
            "stores_creative_text": False,
            "analyzes_pixels": False,
            "database_writes": 0,
            "auto_publication": False,
        },
    )


@router.post("/content-feature-registry/plan")
def plan(body: ContentFeatureRegistryRequest):
    try:
        result = build_content_feature_registry(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return utils.get_response(200, result.model_dump(mode="json"))
