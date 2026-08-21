from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from typing import Any

from app.models.astronomy_director import NarrativeAct, ShotType
from app.models.astromedia import MediaType
from app.models.cinematic_director import (
    CINEMATIC_DIRECTOR_VERSION,
    CinematicDirectionPlan,
    CinematicDirectorRequest,
    CinematicMood,
    CinematicNarrativeRole,
    CinematicPace,
    CinematicSceneDirection,
    CinematicStructuralChecks,
    CinematicStyleProfile,
    CompositionIntent,
    MotionIntent,
    SafeAreaIntent,
    TransitionIntent,
)


class CinematicDirectorError(RuntimeError):
    pass


_ACT_ORDER = {
    NarrativeAct.INTRODUCTION: 0,
    NarrativeAct.DEVELOPMENT: 1,
    NarrativeAct.CLIMAX: 2,
    NarrativeAct.RESOLUTION: 3,
    NarrativeAct.EPILOGUE: 4,
}

_BASE_INTENSITY = {
    NarrativeAct.INTRODUCTION: 0.28,
    NarrativeAct.DEVELOPMENT: 0.50,
    NarrativeAct.CLIMAX: 0.93,
    NarrativeAct.RESOLUTION: 0.52,
    NarrativeAct.EPILOGUE: 0.24,
}

_PROFILE_SHIFT = {
    CinematicStyleProfile.CENTINELA_CINEMATIC: 0.00,
    CinematicStyleProfile.EVENT_EPIC: 0.07,
    CinematicStyleProfile.CELESTIAL_LANDSCAPE: -0.03,
    CinematicStyleProfile.DEEP_SPACE_IMMERSIVE: 0.02,
    CinematicStyleProfile.SCIENTIFIC_EXPLAINER: -0.05,
}

_EVENT_TERMS = {
    "eclipse",
    "meteor",
    "meteoro",
    "lluvia de estrellas",
    "ocultacion",
    "ocultación",
    "conjuncion",
    "conjunción",
    "superluna",
}
_LANDSCAPE_TERMS = {
    "atardecer",
    "amanecer",
    "puesta de sol",
    "salida del sol",
    "crepusculo",
    "crepúsculo",
    "horizonte",
    "paisaje",
}
_DEEP_SPACE_TERMS = {
    "galaxia",
    "galaxy",
    "nebulosa",
    "nebula",
    "cielo profundo",
    "deep sky",
    "cumulo",
    "cúmulo",
}
_EXPLAINER_TERMS = {
    "mision",
    "misión",
    "telescopio",
    "sonda",
    "espectroscopia",
    "instrumento",
    "como funciona",
    "cómo funciona",
}


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold()


def _contains_any(text: str, terms: set[str]) -> bool:
    folded = _fold(text)
    return any(_fold(term) in folded for term in terms)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest().upper()


def _clamp(value: float) -> float:
    return round(max(0.05, min(1.0, value)), 3)


def _infer_profile(request: CinematicDirectorRequest) -> CinematicStyleProfile:
    if request.style_profile != CinematicStyleProfile.AUTO:
        return request.style_profile

    corpus = [request.plan.subject]
    for scene in request.plan.scenes:
        corpus.append(scene.visual_requirement)
        corpus.extend(scene.astronomy_objects)
        corpus.extend(scene.material_keywords)
    text = " ".join(corpus)

    if _contains_any(text, _EVENT_TERMS):
        return CinematicStyleProfile.EVENT_EPIC
    if _contains_any(text, _LANDSCAPE_TERMS):
        return CinematicStyleProfile.CELESTIAL_LANDSCAPE
    if _contains_any(text, _DEEP_SPACE_TERMS):
        return CinematicStyleProfile.DEEP_SPACE_IMMERSIVE
    if _contains_any(text, _EXPLAINER_TERMS):
        return CinematicStyleProfile.SCIENTIFIC_EXPLAINER
    return CinematicStyleProfile.CENTINELA_CINEMATIC


def _validate_alignment(request: CinematicDirectorRequest) -> None:
    plan = request.plan
    base = request.video_base

    if plan.context_hash != base.source_plan_context_hash:
        raise CinematicDirectorError(
            "AstronomyVideoPlan context_hash does not match VideoBasePlan"
        )
    if len(plan.scenes) != base.scene_count:
        raise CinematicDirectorError(
            "scene count mismatch between AstronomyVideoPlan and VideoBasePlan"
        )

    source_by_number = {scene.scene_number: scene for scene in plan.scenes}
    if len(source_by_number) != len(plan.scenes):
        raise CinematicDirectorError("AstronomyVideoPlan has duplicate scene numbers")

    base_by_number = {scene.scene_number: scene for scene in base.scenes}
    if len(base_by_number) != len(base.scenes):
        raise CinematicDirectorError("VideoBasePlan has duplicate scene numbers")

    if set(source_by_number) != set(base_by_number):
        raise CinematicDirectorError("scene numbers are not aligned between F3 and F6")

    for number, source in source_by_number.items():
        base_scene = base_by_number[number]
        if abs(float(source.duration_seconds) - float(base_scene.duration_seconds)) > 0.01:
            raise CinematicDirectorError(
                f"duration mismatch for scene {number}: "
                f"F3={source.duration_seconds} F6={base_scene.duration_seconds}"
            )


def _act_order_valid(plan) -> bool:
    values = [_ACT_ORDER[scene.act] for scene in plan.scenes]
    return values == sorted(values)


def _role_for(scene, *, act_index: int, act_count: int, scene_index: int):
    if scene.act == NarrativeAct.INTRODUCTION:
        return (
            CinematicNarrativeRole.OPENING
            if scene_index == 0
            else CinematicNarrativeRole.ORIENTATION
        )
    if scene.act == NarrativeAct.DEVELOPMENT:
        progress = (act_index + 1) / max(1, act_count)
        return (
            CinematicNarrativeRole.BUILD
            if progress <= 0.5
            else CinematicNarrativeRole.ESCALATION
        )
    if scene.act == NarrativeAct.CLIMAX:
        return CinematicNarrativeRole.PEAK
    if scene.act == NarrativeAct.RESOLUTION:
        return CinematicNarrativeRole.RELEASE
    return CinematicNarrativeRole.AFTERGLOW


def _pace_for(role: CinematicNarrativeRole) -> CinematicPace:
    return {
        CinematicNarrativeRole.OPENING: CinematicPace.MEDITATIVE,
        CinematicNarrativeRole.ORIENTATION: CinematicPace.MEASURED,
        CinematicNarrativeRole.BUILD: CinematicPace.MEASURED,
        CinematicNarrativeRole.ESCALATION: CinematicPace.ACCELERATING,
        CinematicNarrativeRole.PEAK: CinematicPace.PEAK,
        CinematicNarrativeRole.RELEASE: CinematicPace.RELEASE,
        CinematicNarrativeRole.AFTERGLOW: CinematicPace.CONTEMPLATIVE,
    }[role]


def _mood_for(scene) -> CinematicMood:
    if scene.act == NarrativeAct.INTRODUCTION:
        return CinematicMood.MYSTERIOUS
    if scene.act == NarrativeAct.DEVELOPMENT:
        return CinematicMood.DISCOVERY
    if scene.act == NarrativeAct.CLIMAX:
        return CinematicMood.AWE
    if scene.act == NarrativeAct.RESOLUTION:
        return CinematicMood.RELEASE
    return CinematicMood.AFTERGLOW


def _composition_for(shot_type: ShotType) -> CompositionIntent:
    if shot_type in {ShotType.WIDE, ShotType.TIMELAPSE}:
        return CompositionIntent.LAYERED_WIDE
    if shot_type in {
        ShotType.CLOSE_UP,
        ShotType.TELEPHOTO,
        ShotType.DETAIL,
    }:
        return CompositionIntent.SUBJECT_DOMINANT
    if shot_type == ShotType.TRACKING:
        return CompositionIntent.GUIDED_FOLLOW
    if shot_type == ShotType.GRAPHIC:
        return CompositionIntent.INFORMATIONAL_CLEAN
    return CompositionIntent.BALANCED_OBSERVATION


def _motion_for(
    *,
    scene,
    base_scene,
    role: CinematicNarrativeRole,
    prefer_observation: bool,
) -> MotionIntent:
    if base_scene.placeholder:
        return MotionIntent.OBSERVE_LOCKED

    if base_scene.media_type == MediaType.VIDEO:
        if scene.shot_type in {ShotType.TIMELAPSE, ShotType.TRACKING}:
            return MotionIntent.NATURAL_MOTION_ONLY
        if prefer_observation:
            return MotionIntent.NATURAL_MOTION_ONLY

    if role == CinematicNarrativeRole.PEAK:
        return MotionIntent.VERY_SLOW_PUSH
    if role in {
        CinematicNarrativeRole.BUILD,
        CinematicNarrativeRole.ESCALATION,
    }:
        return (
            MotionIntent.OBSERVE_LOCKED
            if prefer_observation
            else MotionIntent.CONTROLLED_REVEAL
        )
    if role == CinematicNarrativeRole.RELEASE:
        return MotionIntent.GENTLE_PULL_BACK
    return MotionIntent.OBSERVE_LOCKED


def _transition_out(
    *,
    scene_index: int,
    scenes,
) -> TransitionIntent:
    current = scenes[scene_index]
    if scene_index == len(scenes) - 1:
        return TransitionIntent.FADE_OUT_INTENT

    next_scene = scenes[scene_index + 1]
    if next_scene.act == NarrativeAct.CLIMAX:
        return TransitionIntent.EMPHASIS_CUT
    if current.act == NarrativeAct.CLIMAX:
        return TransitionIntent.BREATHING_CUT
    if current.act != next_scene.act:
        return TransitionIntent.SOFT_CUT
    return TransitionIntent.MOTIVATED_CUT


def _cut_motivation(scene, transition: TransitionIntent) -> str:
    if transition == TransitionIntent.FADE_OUT_INTENT:
        return "epilogue_completion"
    if transition == TransitionIntent.EMPHASIS_CUT:
        return "enter_climax"
    if transition == TransitionIntent.BREATHING_CUT:
        return "release_after_climax"
    if transition == TransitionIntent.SOFT_CUT:
        return "narrative_act_change"
    return f"continue_{scene.act.value}"


def _future_hints(scene, base_scene, motion: MotionIntent) -> list[str]:
    hints = ["F21_TRANSITION_DIRECTOR_CONSUMER"]

    if scene.shot_type == ShotType.TRACKING:
        hints.append("F11_ASTRONOMICAL_OBJECT_TRACKER_CANDIDATE")

    if base_scene.media_type == MediaType.IMAGE and motion in {
        MotionIntent.VERY_SLOW_PUSH,
        MotionIntent.CONTROLLED_REVEAL,
        MotionIntent.GENTLE_PULL_BACK,
    }:
        hints.append("F13_SMART_KEN_BURNS_CANDIDATE")

    if scene.shot_type != ShotType.GRAPHIC:
        hints.append("F12_SMART_REFRAMING_CANDIDATE")

    return hints


def _directives(
    *,
    role,
    composition,
    motion,
    mood,
    preserve_source_transition,
    source_transition,
) -> list[str]:
    result = [
        f"narrative_role:{role.value}",
        f"composition:{composition.value}",
        f"motion_semantic_only:{motion.value}",
        f"mood:{mood.value}",
        "preserve_astronomical_subject_readability",
        "avoid_gratuitous_motion",
    ]
    if preserve_source_transition and source_transition.strip():
        result.append("source_transition_reference:" + source_transition.strip())
    return result


class CinematicDirector:
    """F7 deterministic cinematic intention layer.

    This service does not render, call FFmpeg, search media, invoke LLMs,
    activate SmartFocal/SemanticMatcher/WanGP, or publish. It only converts
    validated F3 + F6 plans into downstream cinematic direction metadata.
    """

    version = CINEMATIC_DIRECTOR_VERSION

    def build(self, request: CinematicDirectorRequest) -> CinematicDirectionPlan:
        _validate_alignment(request)

        plan = request.plan
        base = request.video_base

        if not _act_order_valid(plan):
            raise CinematicDirectorError(
                "narrative acts are not ordered introduction→development→"
                "climax→resolution→epilogue"
            )

        climax_scenes = [
            scene for scene in plan.scenes if scene.act == NarrativeAct.CLIMAX
        ]
        if not climax_scenes:
            raise CinematicDirectorError("AstronomyVideoPlan has no climax scene")

        if not any(scene.act == NarrativeAct.EPILOGUE for scene in plan.scenes):
            raise CinematicDirectorError("AstronomyVideoPlan has no epilogue scene")

        profile = _infer_profile(request)
        profile_shift = _PROFILE_SHIFT[profile]

        act_positions: dict[NarrativeAct, int] = {}
        act_counts: dict[NarrativeAct, int] = {}
        for scene in plan.scenes:
            act_counts[scene.act] = act_counts.get(scene.act, 0) + 1

        base_by_number = {scene.scene_number: scene for scene in base.scenes}
        directions: list[CinematicSceneDirection] = []

        for scene_index, scene in enumerate(plan.scenes):
            act_index = act_positions.get(scene.act, 0)
            act_positions[scene.act] = act_index + 1
            act_count = act_counts[scene.act]

            role = _role_for(
                scene,
                act_index=act_index,
                act_count=act_count,
                scene_index=scene_index,
            )

            intensity = _BASE_INTENSITY[scene.act]

            if scene.act == NarrativeAct.DEVELOPMENT:
                progress = (act_index + 1) / max(1, act_count)
                intensity += 0.10 * progress

            # Keep climax structurally dominant regardless of user bias/profile.
            if scene.act == NarrativeAct.CLIMAX:
                intensity = max(0.90, intensity + profile_shift + request.intensity_bias)
            else:
                intensity += profile_shift + request.intensity_bias

            intensity = _clamp(intensity)

            base_scene = base_by_number[scene.scene_number]
            composition = _composition_for(scene.shot_type)
            motion = _motion_for(
                scene=scene,
                base_scene=base_scene,
                role=role,
                prefer_observation=request.prefer_observation_over_motion,
            )
            transition = _transition_out(
                scene_index=scene_index,
                scenes=plan.scenes,
            )
            mood = _mood_for(scene)

            warnings = []
            if base_scene.placeholder:
                warnings.append("PLACEHOLDER_DIRECTION_ONLY")
            if base_scene.warnings:
                warnings.extend("F6:" + warning for warning in base_scene.warnings)

            directions.append(
                CinematicSceneDirection(
                    scene_number=scene.scene_number,
                    act=scene.act,
                    duration_seconds=float(scene.duration_seconds),
                    source_shot_type=scene.shot_type,
                    source_transition=scene.transition,
                    visual_requirement=scene.visual_requirement,
                    material_selection_status=base_scene.material_selection_status,
                    placeholder=base_scene.placeholder,
                    execution_ready=not base_scene.placeholder,
                    narrative_role=role,
                    pace=_pace_for(role),
                    intensity=intensity,
                    mood=mood,
                    composition_intent=composition,
                    motion_intent=motion,
                    transition_out_intent=transition,
                    cut_motivation=_cut_motivation(scene, transition),
                    continuity_group="act:" + scene.act.value,
                    safe_area=SafeAreaIntent(),
                    directives=_directives(
                        role=role,
                        composition=composition,
                        motion=motion,
                        mood=mood,
                        preserve_source_transition=request.preserve_source_transition_intent,
                        source_transition=scene.transition,
                    ),
                    future_phase_hints=_future_hints(scene, base_scene, motion),
                    warnings=warnings,
                )
            )

        # Force the chosen climax above every non-climax after all shifts.
        chosen_climax = climax_scenes[0].scene_number
        max_non_climax = max(
            (
                direction.intensity
                for direction in directions
                if direction.scene_number != chosen_climax
            ),
            default=0.0,
        )
        for direction in directions:
            if direction.scene_number == chosen_climax:
                direction.intensity = _clamp(max(direction.intensity, max_non_climax + 0.08))

        checks = CinematicStructuralChecks(
            act_order_valid=True,
            climax_present=True,
            epilogue_present=True,
            scene_number_alignment=[
                scene.scene_number for scene in plan.scenes
            ]
            == [
                scene.scene_number for scene in base.scenes
            ],
            duration_alignment=all(
                abs(
                    float(scene.duration_seconds)
                    - float(base_by_number[scene.scene_number].duration_seconds)
                )
                <= 0.01
                for scene in plan.scenes
            ),
            placeholders_preserved=sum(scene.placeholder for scene in directions)
            == base.placeholder_count,
        )

        hash_payload = {
            "version": self.version,
            "source_plan_context_hash": plan.context_hash,
            "source_video_base_version": base.version,
            "source_selector_version": base.source_selector_version,
            "style_profile": profile.value,
            "intensity_bias": request.intensity_bias,
            "prefer_observation_over_motion": request.prefer_observation_over_motion,
            "preserve_source_transition_intent": request.preserve_source_transition_intent,
            "scenes": [
                direction.model_dump(mode="json")
                for direction in directions
            ],
        }

        return CinematicDirectionPlan(
            subject=plan.subject,
            source_plan_context_hash=plan.context_hash,
            source_video_base_version=base.version,
            source_selector_version=base.source_selector_version,
            style_profile=profile,
            scene_count=len(directions),
            placeholder_count=sum(scene.placeholder for scene in directions),
            total_duration_seconds=round(
                sum(scene.duration_seconds for scene in directions),
                4,
            ),
            climax_scene_number=chosen_climax,
            tension_curve=[scene.intensity for scene in directions],
            direction_hash=_hash_json(hash_payload),
            structural_checks=checks,
            scenes=directions,
            generated_at_utc=datetime.now(timezone.utc),
        )
