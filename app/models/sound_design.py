from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.cinematic_infographics import CinematicInfographicsPlan
from app.models.transition_director import TransitionDirectorPlan
from app.models.visual_story_graph import VisualStoryGraph


SOUND_DESIGN_VERSION = "sound-design-v0.1"


class StrictSoundDesignModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SoundCueType(str, Enum):
    ATMOSPHERIC_BED = "ATMOSPHERIC_BED"
    CLIMAX_ACCENT = "CLIMAX_ACCENT"


class SoundRole(str, Enum):
    NON_DIEGETIC_DESIGN = "NON_DIEGETIC_DESIGN"


class SoundDesignRequest(StrictSoundDesignModel):
    story_graph: VisualStoryGraph
    infographics: CinematicInfographicsPlan
    transitions: TransitionDirectorPlan


class SoundCue(StrictSoundDesignModel):
    cue_id: str
    scene_number: int = Field(ge=1)
    cue_type: SoundCueType
    role: SoundRole = SoundRole.NON_DIEGETIC_DESIGN
    design_profile: str
    intensity: float = Field(ge=0.0, le=1.0)

    asset_selected: bool = False
    asset_path: str | None = None
    license_status: str = "LICENCIA_NO_VERIFICADA"
    publication_eligible: bool = False
    requires_human_selection: bool = True

    diegetic_space_sound: bool = False

    @model_validator(mode="after")
    def validate_cue(self):
        if self.asset_selected or self.asset_path is not None:
            raise ValueError("F22 V0.1 does not select audio assets")
        if self.license_status != "LICENCIA_NO_VERIFICADA":
            raise ValueError("F22 cannot verify license without selected asset")
        if self.publication_eligible:
            raise ValueError("unselected F22 cue cannot be publication eligible")
        if not self.requires_human_selection:
            raise ValueError("F22 requires human asset selection")
        if self.diegetic_space_sound:
            raise ValueError("F22 forbids invented diegetic sound in vacuum")
        return self


class SoundDesignPlan(StrictSoundDesignModel):
    version: str = SOUND_DESIGN_VERSION
    subject: str
    source_plan_context_hash: str
    source_story_graph_hash: str
    source_infographics_hash: str
    source_transition_director_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_audio: bool = False
    generates_audio: bool = False
    downloads_audio: bool = False
    searches_audio: bool = False
    selects_assets: bool = False
    verifies_external_licenses: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    cue_count: int = Field(ge=0)
    asset_count: int = Field(default=0, ge=0)
    climax_accent_count: int = Field(ge=0)

    cues: list[SoundCue]
    sound_design_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.cue_count != len(self.cues):
            raise ValueError("cue_count mismatch")
        if self.asset_count != 0:
            raise ValueError("F22 V0.1 must not select assets")
        if self.climax_accent_count != sum(
            cue.cue_type == SoundCueType.CLIMAX_ACCENT
            for cue in self.cues
        ):
            raise ValueError("climax_accent_count mismatch")
        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.renders_audio
            or self.generates_audio
            or self.downloads_audio
            or self.searches_audio
            or self.selects_assets
            or self.verifies_external_licenses
            or self.auto_publication
        ):
            raise ValueError("F22 guardrail violation")
        return self
