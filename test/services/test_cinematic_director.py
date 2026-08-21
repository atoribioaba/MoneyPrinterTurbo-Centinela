from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import (
    AstronomyVideoPlan,
    GenerationOrigin,
    NarrativeAct,
    ScenePlan,
    ShotType,
)
from app.models.cinematic_director import (
    CinematicDirectorRequest,
    CinematicNarrativeRole,
    CinematicStyleProfile,
    MotionIntent,
    TransitionIntent,
)
from app.models.material_selection import SelectionStatus
from app.models.video_base import (
    VideoBaseBlockCode,
    VideoBasePlan,
    VideoBaseRenderAction,
    VideoBaseRenderMode,
    VideoBaseScenePlan,
)
from app.models.schema import VideoFitMode
from app.services.cinematic_director import CinematicDirector, CinematicDirectorError


def astronomy_plan(subject="Moon test"):
    acts = [
        NarrativeAct.INTRODUCTION,
        NarrativeAct.DEVELOPMENT,
        NarrativeAct.CLIMAX,
        NarrativeAct.RESOLUTION,
        NarrativeAct.EPILOGUE,
    ]
    shots = [
        ShotType.WIDE,
        ShotType.MEDIUM,
        ShotType.TELEPHOTO,
        ShotType.STATIC,
        ShotType.WIDE,
    ]

    scenes = [
        ScenePlan(
            scene_number=index,
            act=acts[index - 1],
            duration_seconds=5,
            narration=f"Narration {index}",
            visual_requirement=f"Visual {index}",
            astronomy_objects=["Moon"],
            shot_type=shots[index - 1],
            material_keywords=["moon"],
            source_priority=["OWN_MEDIA"],
            transition="cut",
            claims=[],
            ai_recreation_allowed=False,
            scientific_status=ScientificStatus.HECHO_VERIFICADO,
        )
        for index in range(1, 6)
    ]

    return AstronomyVideoPlan(
        subject=subject,
        hook="Hook",
        scientific_context_summary="Context",
        narrative_arc=acts,
        scenes=scenes,
        epilogue="End",
        context_hash="ctx-f7",
        generation_origin=GenerationOrigin.LLM_VALIDATED,
        model_used="test",
        repair_attempted=False,
        total_duration_seconds=25,
        requires_human_review=True,
        approved_for_publication=False,
        generated_at_utc=datetime.now(timezone.utc),
    )


def video_base_plan(plan=None):
    plan = plan or astronomy_plan()

    scenes = [
        VideoBaseScenePlan(
            scene_number=scene.scene_number,
            scene_key=f"ctx-f7:scene:{scene.scene_number}",
            duration_seconds=float(scene.duration_seconds),
            visual_requirement=scene.visual_requirement,
            narration=scene.narration,
            material_selection_status=SelectionStatus.NO_ADEQUATE_MEDIA,
            render_action=VideoBaseRenderAction.PLACEHOLDER,
            fit_mode=VideoFitMode.fit,
            focal_x=0.5,
            focal_y=0.5,
            renderable=True,
            clean_base_eligible=False,
            placeholder=True,
            placeholder_reason=VideoBaseBlockCode.NO_ADEQUATE_MEDIA,
        )
        for scene in plan.scenes
    ]

    return VideoBasePlan(
        subject=plan.subject,
        source_plan_context_hash=plan.context_hash,
        source_selector_version="material-selection-v0.1",
        render_mode=VideoBaseRenderMode.REVIEW_PARTIAL,
        requested_codec="h264_nvenc",
        scene_count=len(scenes),
        unresolved_count=len(scenes),
        placeholder_count=len(scenes),
        clean_base_eligible=False,
        source_materials_publication_ready=False,
        scenes=scenes,
        generated_at_utc=datetime.now(timezone.utc),
    )


def request(plan=None, **kwargs):
    plan = plan or astronomy_plan()
    return CinematicDirectorRequest(
        plan=plan,
        video_base=video_base_plan(plan),
        **kwargs,
    )


def test_builds_five_scene_direction_plan_with_climax_peak():
    result = CinematicDirector().build(request())

    assert result.scene_count == 5
    assert result.placeholder_count == 5
    assert result.climax_scene_number == 3
    assert result.tension_curve[2] == max(result.tension_curve)
    assert result.scenes[2].narrative_role == CinematicNarrativeRole.PEAK
    assert result.scenes[-1].transition_out_intent == TransitionIntent.FADE_OUT_INTENT


def test_direction_hash_is_deterministic():
    director = CinematicDirector()

    first = director.build(request())
    second = director.build(request())

    assert first.direction_hash == second.direction_hash
    assert first.tension_curve == second.tension_curve


def test_placeholders_are_preserved_and_never_execution_ready():
    result = CinematicDirector().build(request())

    assert all(scene.placeholder for scene in result.scenes)
    assert all(not scene.execution_ready for scene in result.scenes)
    assert all(
        scene.motion_intent == MotionIntent.OBSERVE_LOCKED
        for scene in result.scenes
    )
    assert all(
        "PLACEHOLDER_DIRECTION_ONLY" in scene.warnings
        for scene in result.scenes
    )


def test_auto_profile_detects_eclipse_as_event_epic():
    plan = astronomy_plan(subject="Eclipse total de Luna")
    result = CinematicDirector().build(request(plan))

    assert result.style_profile == CinematicStyleProfile.EVENT_EPIC


def test_f7_does_not_trigger_heavy_or_render_subsystems():
    result = CinematicDirector().build(request())

    assert result.deterministic is True
    assert result.uses_llm is False
    assert result.gpu_required is False
    assert result.renders_video is False
    assert result.searches_material is False
    assert result.auto_publication is False


def test_context_mismatch_is_rejected():
    plan = astronomy_plan()
    base = video_base_plan(plan)
    base.source_plan_context_hash = "wrong-context"

    with pytest.raises(CinematicDirectorError):
        CinematicDirector().build(
            CinematicDirectorRequest(
                plan=plan,
                video_base=base,
            )
        )


def test_duration_mismatch_is_rejected():
    plan = astronomy_plan()
    base = video_base_plan(plan)
    base.scenes[0].duration_seconds = 6.0

    with pytest.raises(CinematicDirectorError):
        CinematicDirector().build(
            CinematicDirectorRequest(
                plan=plan,
                video_base=base,
            )
        )
