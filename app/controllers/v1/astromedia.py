from fastapi import (
    HTTPException,
)

from app.controllers.v1.base import (
    new_router,
)

from app.models.astromedia import (
    IndexRequest,
    OverrideRequest,
    SearchRequest,
)

from app.services.astromedia import (
    AstroMediaCatalog,
    AstroMediaError,
)

from app.utils import utils


router = new_router()

_catalog: AstroMediaCatalog | None = None


def get_catalog() -> AstroMediaCatalog:
    global _catalog

    if _catalog is None:
        _catalog = AstroMediaCatalog()

    return _catalog


@router.get("/astromedia/health")
def health():
    catalog = get_catalog()
    items = catalog.list_items(False)

    active = [item for item in items if item.active]

    return utils.get_response(
        200,
        {
            "status": "ok",
            "media_root": r"D:\ASTRONOMÍA\Medios",
            "media_root_mode": "read_only",
            "active_item_count": len(active),
            "publication_eligible_count": sum(
                item.publication_eligible for item in active
            ),
            "network_required_at_runtime": False,
            "provider_download_triggered": False,
            "semantic_model_required": False,
            "media_files_modified_by_catalog": False,
        },
    )


@router.post("/astromedia/index")
def index(
    body: IndexRequest,
):
    catalog = get_catalog()

    try:
        report = catalog.index_library(body)

    except AstroMediaError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return utils.get_response(
        200,
        report.model_dump(mode="json"),
    )


@router.post("/astromedia/search")
def search(
    body: SearchRequest,
):
    catalog = get_catalog()

    return utils.get_response(
        200,
        [result.model_dump(mode="json") for result in catalog.search(body)],
    )


@router.get("/astromedia/item")
def item(
    media_id: str,
):
    catalog = get_catalog()
    value = catalog.get(media_id)

    if not value:
        raise HTTPException(
            status_code=404,
            detail="Unknown media_id",
        )

    return utils.get_response(
        200,
        value.model_dump(mode="json"),
    )


@router.post("/astromedia/override")
def override(
    body: OverrideRequest,
):
    catalog = get_catalog()

    try:
        catalog.set_override(
            body.scene_key,
            body.media_id,
        )

    except AstroMediaError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return utils.get_response(
        200,
        {
            "scene_key": body.scene_key,
            "media_id": body.media_id,
        },
    )


@router.delete("/astromedia/override")
def clear_override(
    scene_key: str,
):
    catalog = get_catalog()
    previous = catalog.get_override(scene_key)

    catalog.clear_override(scene_key)

    return utils.get_response(
        200,
        {
            "scene_key": scene_key,
            "media_id": previous,
        },
    )
