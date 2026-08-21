"""Application configuration - root APIRouter.

Defines all FastAPI application endpoints.
"""

from fastapi import APIRouter

from app.controllers.v1 import (
    astronomical_tracker,
    astronomy,
    astronomy_director,
    astromedia,
    best_moment,
    cinematic_director,
    llm,
    master_image_i2v,
    material_selection,
    shot_quality,
    smart_ken_burns,
    smart_reframing,
    video,
    video_base,
    visual_story_graph,
    astronomy_motion_graphics,
    cinematic_infographics,
    wangp_backend,
    depth_parallax,
    color_science,
    shot_matching,
    transition_director,
    sound_design,
    voice_studio,
    audio_mastering,

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
root_api_router.include_router(shot_quality.router)
root_api_router.include_router(best_moment.router)
root_api_router.include_router(astronomical_tracker.router)
root_api_router.include_router(smart_reframing.router)
root_api_router.include_router(smart_ken_burns.router)
root_api_router.include_router(master_image_i2v.router)
root_api_router.include_router(wangp_backend.router)
root_api_router.include_router(astronomy_motion_graphics.router)
root_api_router.include_router(cinematic_infographics.router)
root_api_router.include_router(depth_parallax.router)
root_api_router.include_router(color_science.router)
root_api_router.include_router(shot_matching.router)
root_api_router.include_router(transition_director.router)
root_api_router.include_router(sound_design.router)
root_api_router.include_router(voice_studio.router)
root_api_router.include_router(audio_mastering.router)
