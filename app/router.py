"""Application configuration - root APIRouter.

Defines all FastAPI application endpoints.
"""

from fastapi import APIRouter

from app.controllers.v1 import (
    astronomical_tracker, astronomy, astronomy_director, astromedia, best_moment, cinematic_director, llm,
    master_image_i2v, material_selection, shot_quality, smart_ken_burns, smart_reframing, video, video_base,
    visual_story_graph, astronomy_motion_graphics, cinematic_infographics, wangp_backend, depth_parallax,
    color_science, shot_matching, transition_director, sound_design, voice_studio, audio_mastering,
    subtitle_intelligence, selective_upscaling, media_mining, quality_comparator, quality_gates, delivery_render,
    analytics_brain, metric_normalizer, performance_signals, retention_intelligence, experiment_planner,
    content_feature_registry, outcome_linker, association_analyzer, experiment_evidence_ledger, evidence_recommendation_gate,
    policy_candidate,
    policy_simulator,
    policy_comparator,
    human_policy_approval,
    policy_registry,
    shadow_policy_evaluator,
    canary_policy_planner,
    canary_monitor,
    rollback_decision_gate,
    controlled_promotion_gate,

)

root_api_router = APIRouter()
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
root_api_router.include_router(subtitle_intelligence.router)
root_api_router.include_router(selective_upscaling.router)
root_api_router.include_router(media_mining.router)
root_api_router.include_router(quality_comparator.router)
root_api_router.include_router(quality_gates.router)
root_api_router.include_router(delivery_render.router)
root_api_router.include_router(analytics_brain.router)
root_api_router.include_router(metric_normalizer.router)
root_api_router.include_router(performance_signals.router)
root_api_router.include_router(retention_intelligence.router)
root_api_router.include_router(experiment_planner.router)
root_api_router.include_router(content_feature_registry.router)
root_api_router.include_router(outcome_linker.router)
root_api_router.include_router(association_analyzer.router)
root_api_router.include_router(experiment_evidence_ledger.router)
root_api_router.include_router(evidence_recommendation_gate.router)
root_api_router.include_router(policy_candidate.router)
root_api_router.include_router(policy_simulator.router)
root_api_router.include_router(policy_comparator.router)
root_api_router.include_router(human_policy_approval.router)
root_api_router.include_router(policy_registry.router)
root_api_router.include_router(shadow_policy_evaluator.router)
root_api_router.include_router(canary_policy_planner.router)
root_api_router.include_router(canary_monitor.router)
root_api_router.include_router(rollback_decision_gate.router)
root_api_router.include_router(controlled_promotion_gate.router)
