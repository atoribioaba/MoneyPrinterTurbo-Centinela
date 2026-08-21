"""Application configuration - root APIRouter.

Defines all FastAPI application endpoints.

Resources:
    1. https://fastapi.tiangolo.com/tutorial/bigger-applications

"""

from fastapi import APIRouter

from app.controllers.v1 import (
    astronomy,
    astronomy_director,
    astromedia,
    cinematic_director,
    llm,
    material_selection,
    video,
    video_base,
    visual_story_graph,
)

root_api_router = APIRouter()
# v1
root_api_router.include_router(video.router)
root_api_router.include_router(llm.router)
root_api_router.include_router(astronomy.router)
root_api_router.include_router(astronomy_director.router)
root_api_router.include_router(astromedia.router)
root_api_router.include_router(material_selection.router)
root_api_router.include_router(video_base.router)
root_api_router.include_router(cinematic_director.router)
root_api_router.include_router(visual_story_graph.router)
