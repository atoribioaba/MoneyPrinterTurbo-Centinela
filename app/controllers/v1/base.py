from fastapi import APIRouter, Depends

from app.controllers import base as auth_base


def new_router(dependencies=None):
    # All V1 routes are authenticated by default.
    #
    # Empty app.api_key preserves backward-compatible local/open mode.
    # Explicit dependencies remain supported for upstream routers such as
    # video and llm. An explicit [] can intentionally opt out if a future
    # route has a documented reason to remain public.
    if dependencies is None:
        dependencies = [Depends(auth_base.verify_token)]

    router = APIRouter()
    router.tags = ["V1"]
    router.prefix = "/api/v1"

    if dependencies:
        router.dependencies = dependencies

    return router
