from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astronomy import ScientificStatus
from app.models.astronomy_director import AstronomyVideoPlan
from app.models.astronomy_motion_graphics import AstronomyMotionGraphicsPlan


CINEMATIC_INFOGRAPHICS_VERSION = "cinematic-infographics-v0.1"


class StrictInfographicModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class InfographicCardType(str, Enum):
    VERIFIED_FACT = "VERIFIED_FACT"
    APPROXIMATION = "APPROXIMATION"
    HYPOTHESIS = "HYPOTHESIS"
    VISUAL_RECREATION = "VISUAL_RECREATION"
    INFERENCE = "INFERENCE"
    UNVERIFIED = "UNVERIFIED"


class InfographicLayout(str, Enum):
    MINIMAL_FACT_CARD = "MINIMAL_FACT_CARD"
    CINEMATIC_SIDE_CARD = "CINEMATIC_SIDE_CARD"


class InfographicCard(StrictInfographicModel):
    card_id: str
    scene_number: int = Field(ge=1)
    card_type: InfographicCardType
    layout: InfographicLayout

    statement: str = Field(min_length=1, max_length=400)
    scientific_status: ScientificStatus
    fact_ids: list[str] = Field(default_factory=list)

    source_is_plan_claim: bool = True
    external_data_added: bool = False
    numeric_value_invented: bool = False
    chart_invented: bool = False

    grounding_ready: bool
    human_review_required: bool = True

    @model_validator(mode="after")
    def validate_card(self):
        if (
            self.scientific_status == ScientificStatus.HECHO_VERIFICADO
            and not self.fact_ids
        ):
            raise ValueError("verified infographic requires fact_ids")
        if (
            not self.source_is_plan_claim
            or self.external_data_added
            or self.numeric_value_invented
            or self.chart_invented
        ):
            raise ValueError("F17 infographic grounding violation")
        if not self.human_review_required:
            raise ValueError(
                "F17 never bypasses GENERAR -> REVISAR -> APROBAR -> PUBLICAR"
            )
        return self


class InfographicScene(StrictInfographicModel):
    scene_number: int = Field(ge=1)
    card_count: int = Field(ge=0)
    cards: list[InfographicCard] = Field(default_factory=list)
    human_review_required: bool = True

    @model_validator(mode="after")
    def validate_count(self):
        if self.card_count != len(self.cards):
            raise ValueError("card_count mismatch")
        return self


class InfographicStructuralChecks(StrictInfographicModel):
    source_plan_alignment: bool
    motion_graphics_hash_preserved: bool
    plan_claims_only: bool
    fact_ids_preserved: bool
    scientific_status_preserved: bool
    no_external_data_added: bool
    no_invented_numbers: bool
    no_invented_charts: bool


class CinematicInfographicsPlan(StrictInfographicModel):
    version: str = CINEMATIC_INFOGRAPHICS_VERSION
    subject: str
    source_plan_context_hash: str
    source_motion_graphics_version: str
    source_motion_graphics_hash: str

    deterministic: bool = True
    planning_only: bool = True
    resource_class: str = "LIGHT"

    uses_llm: bool = False
    gpu_required: bool = False
    renders_infographics: bool = False
    downloads_assets: bool = False
    searches_web: bool = False
    computes_astronomy: bool = False
    auto_publication: bool = False

    scene_count: int = Field(ge=1)
    card_count: int = Field(ge=0)
    verified_card_count: int = Field(ge=0)
    grounding_ready_count: int = Field(ge=0)
    human_review_required_count: int = Field(ge=0)

    scenes: list[InfographicScene]
    structural_checks: InfographicStructuralChecks

    infographics_hash: str
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_plan(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count mismatch")

        cards = [card for scene in self.scenes for card in scene.cards]
        if self.card_count != len(cards):
            raise ValueError("card_count mismatch")
        if self.verified_card_count != sum(
            card.card_type == InfographicCardType.VERIFIED_FACT
            for card in cards
        ):
            raise ValueError("verified_card_count mismatch")
        if self.grounding_ready_count != sum(
            card.grounding_ready for card in cards
        ):
            raise ValueError("grounding_ready_count mismatch")
        if self.human_review_required_count != sum(
            card.human_review_required for card in cards
        ):
            raise ValueError("human_review_required_count mismatch")

        if not all(self.structural_checks.model_dump().values()):
            raise ValueError("all F17 structural checks must pass")

        if (
            not self.planning_only
            or self.uses_llm
            or self.gpu_required
            or self.renders_infographics
            or self.downloads_assets
            or self.searches_web
            or self.computes_astronomy
            or self.auto_publication
        ):
            raise ValueError("F17 guardrail violation")

        return self
