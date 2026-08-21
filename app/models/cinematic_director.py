from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astronomy_director import AstronomyVideoPlan, NarrativeAct, ShotType
from app.models.material_selection import SelectionStatus
from app.models.video_base import VideoBasePlan


CINEMATIC_DIRECTOR_VERSION = "cinematic-director-v0.1"


class StrictCinematicModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class CinematicStyleProfile(str, Enum):
    AUTO = "AUTO"
    CENTINELA_CINEMATIC = "CENTINELA_CINEMATIC"
    EVENT_EPIC = "EVENT_EPIC"
    CELESTIAL_LANDSCAPE = "CELESTIAL_LANDSCAPE"
    DEEP_SPACE_IMMERSIVE = "DEEP_SPACE_IMMERSIVE"
    SCIENTIFIC_EXPLAINER = "SCIENTIFIC_EXPLAINER"


class CinematicNarrativeRole(str, Enum):
    OPENING = "OPENING"
    ORIENTATION = "ORIENTATION"
    BUILD = "BUILD"
    ESCALATION = "ESCALATION"
    PEAK = "PEAK"
    RELEASE = "RELEASE"
    AFTERGLOW = "AFTERGLOW"


class CinematicPace(str, Enum):
    MEDITATIVE = "MEDITATIVE"
    MEASURED = "MEASURED"
    ACCELERATING = "ACCELERATING"
    PEAK = "PEAK"
    RELEASE = "RELEASE"
    CONTEMPLATIVE = "CONTEMPLATIVE"


class CompositionIntent(str, Enum):
    LAYERED_WIDE = "LAYERED_WIDE"
    BALANCED_OBSERVATION = "BALANCED_OBSERVATION"
    SUBJECT_DOMINANT = "SUBJECT_DOMINANT"
    GUIDED_FOLLOW = "GUIDED_FOLLOW"
    INFORMATIONAL_CLEAN = "INFORMATIONAL_CLEAN"


class MotionIntent(str, Enum):
    OBSERVE_LOCKED = "OBSERVE_LOCKED"
    NATURAL_MOTION_ONLY = "NATURAL_MOTION_ONLY"
    VERY_SLOW_PUSH = "VERY_SLOW_PUSH"
    CONTROLLED_REVEAL = "CONTROLLED_REVEAL"
    GENTLE_PULL_BACK = "GENTLE_PULL_BACK"


class TransitionIntent(str, Enum):
    OPEN = "OPEN"
    MOTIVATED_CUT = "MOTIVATED_CUT"
    SOFT_CUT = "SOFT_CUT"
    EMPHASIS_CUT = "EMPHASIS_CUT"
    BREATHING_CUT = "BREATHING_CUT"
    FADE_OUT_INTENT = "FADE_OUT_INTENT"


class CinematicMood(str, Enum):
    MYSTERIOUS = "MYSTERIOUS"
    CONTEMPLATIVE = "CONTEMPLATIVE"
    DISCOVERY = "DISCOVERY"
    AWE = "AWE"
    RELEASE = "RELEASE"
    AFTERGLOW = "AFTERGLOW"


class SafeAreaIntent(StrictCinematicModel):
    top_fraction: float = Field(default=0.08, ge=0.0, le=0.4)
    bottom_fraction: float = Field(default=0.20, ge=0.0, le=0.5)
    left_fraction: float = Field(default=0.06, ge=0.0, le=0.3)
    right_fraction: float = Field(default=0.06, ge=0.0, le=0.3)


class CinematicDirectorRequest(StrictCinematicModel):
    plan: AstronomyVideoPlan
    video_base: VideoBasePlan
    style_profile: CinematicStyleProfile = CinematicStyleProfile.AUTO
    intensity_bias: float = Field(default=0.0, ge=-0.20, le=0.20)
    prefer_observation_over_motion: bool = True
    preserve_source_transition_intent: bool = True


class CinematicSceneDirection(StrictCinematicModel):
    scene_number: int = Field(ge=1)
    act: NarrativeAct
    duration_seconds: float = Field(gt=0.0)
    source_shot_type: ShotType
    source_transition: str
    visual_requirement: str

    material_selection_status: SelectionStatus
    placeholder: bool
    execution_ready: bool

    narrative_role: CinematicNarrativeRole
    pace: CinematicPace
    intensity: float = Field(ge=0.0, le=1.0)
    mood: CinematicMood

    composition_intent: CompositionIntent
    motion_intent: MotionIntent
    transition_out_intent: TransitionIntent
    cut_motivation: str
    continuity_group: str

    safe_area: SafeAreaIntent = Field(default_factory=SafeAreaIntent)
    directives: list[str] = Field(default_factory=list)
    future_phase_hints: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CinematicStructuralChecks(StrictCinematicModel):
    act_order_valid: bool
    climax_present: bool
    epilogue_present: bool
    scene_number_alignment: bool
    duration_alignment: bool
    placeholders_preserved: bool


class CinematicDirectionPlan(StrictCinematicModel):
    version: str = CINEMATIC_DIRECTOR_VERSION
    subject: str
    source_plan_context_hash: str
    source_video_base_version: str
    source_selector_version: str

    style_profile: CinematicStyleProfile
    deterministic: bool = True
    uses_llm: bool = False
    gpu_required: bool = False
    renders_video: bool = False
    searches_material: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    placeholder_count: int = Field(ge=0)
    total_duration_seconds: float = Field(gt=0.0)
    climax_scene_number: int = Field(ge=1)
    tension_curve: list[float]
    direction_hash: str

    structural_checks: CinematicStructuralChecks
    scenes: list[CinematicSceneDirection]
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_contract(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count must equal scenes length")
        if self.placeholder_count != sum(scene.placeholder for scene in self.scenes):
            raise ValueError("placeholder_count mismatch")
        if len(self.tension_curve) != self.scene_count:
            raise ValueError("tension_curve length mismatch")
        if [scene.intensity for scene in self.scenes] != self.tension_curve:
            raise ValueError("tension_curve must match scene intensities")
        numbers = [scene.scene_number for scene in self.scenes]
        if len(numbers) != len(set(numbers)):
            raise ValueError("scene numbers must be unique")
        if self.climax_scene_number not in numbers:
            raise ValueError("climax_scene_number must exist")
        peak = max(self.scenes, key=lambda scene: scene.intensity)
        if peak.scene_number != self.climax_scene_number:
            raise ValueError("climax scene must be the intensity peak")
        actual_duration = round(sum(scene.duration_seconds for scene in self.scenes), 4)
        if abs(actual_duration - self.total_duration_seconds) > 0.01:
            raise ValueError("total_duration_seconds mismatch")
        checks = self.structural_checks
        if not all(
            (
                checks.act_order_valid,
                checks.climax_present,
                checks.epilogue_present,
                checks.scene_number_alignment,
                checks.duration_alignment,
                checks.placeholders_preserved,
            )
        ):
            raise ValueError("structural checks must all pass")
        if self.uses_llm or self.gpu_required or self.renders_video or self.searches_material:
            raise ValueError("F7 V0.1 is planning-only, CPU-light and deterministic")
        if self.auto_publication:
            raise ValueError("F7 must never auto-publish")
        return self
