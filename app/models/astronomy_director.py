from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.astronomy import AstronomyContextRequest, ScientificStatus
from app.models.schema import BaseResponse


class StrictDirectorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class NarrativeAct(str, Enum):
    INTRODUCTION = "introduction"
    DEVELOPMENT = "development"
    CLIMAX = "climax"
    RESOLUTION = "resolution"
    EPILOGUE = "epilogue"


class ShotType(str, Enum):
    WIDE = "wide"
    MEDIUM = "medium"
    CLOSE_UP = "close_up"
    TELEPHOTO = "telephoto"
    TIMELAPSE = "timelapse"
    STATIC = "static"
    TRACKING = "tracking"
    DETAIL = "detail"
    GRAPHIC = "graphic"


class DirectorBackend(str, Enum):
    OLLAMA_LOCAL = "ollama_local"


class GenerationOrigin(str, Enum):
    LLM_VALIDATED = "LLM_VALIDATED"
    LLM_REPAIRED = "LLM_REPAIRED"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


class GroundingFact(StrictDirectorModel):
    fact_id: str
    label_es: str
    value: Any
    unit: str | None = None
    scientific_status: ScientificStatus
    source_ids: list[str] = Field(default_factory=list)


class GroundingPacket(StrictDirectorModel):
    context_hash: str
    facts: list[GroundingFact]
    source_ids: list[str] = Field(default_factory=list)


class PlanScientificClaim(StrictDirectorModel):
    statement: str = Field(min_length=1, max_length=400)
    fact_ids: list[str] = Field(default_factory=list)
    scientific_status: ScientificStatus

    @model_validator(mode="after")
    def verified_claim_requires_grounding(self):
        if (
            self.scientific_status == ScientificStatus.HECHO_VERIFICADO
            and not self.fact_ids
        ):
            raise ValueError("HECHO_VERIFICADO claims require grounding fact_ids")
        return self


class ScenePlan(StrictDirectorModel):
    scene_number: int = Field(ge=1, le=20)
    act: NarrativeAct
    duration_seconds: int = Field(ge=2, le=45)
    narration: str = Field(min_length=1, max_length=1200)
    visual_requirement: str = Field(min_length=1, max_length=1200)
    astronomy_objects: list[str] = Field(default_factory=list)
    shot_type: ShotType
    material_keywords: list[str] = Field(default_factory=list, max_length=8)
    source_priority: list[str] = Field(default_factory=list)
    transition: str = Field(min_length=1, max_length=200)
    claims: list[PlanScientificClaim] = Field(default_factory=list)
    ai_recreation_allowed: bool = False
    scientific_status: ScientificStatus

    @field_validator("material_keywords")
    @classmethod
    def normalize_keywords(cls, value):
        result = []
        seen = set()
        for item in value:
            item = item.strip()
            key = item.casefold()
            if item and key not in seen:
                seen.add(key)
                result.append(item)
        return result


class AstronomyVideoPlanDraft(StrictDirectorModel):
    subject: str = Field(min_length=3, max_length=300)
    language: str = "es-ES"
    audience: str = "divulgación astronómica general"
    hook: str = Field(min_length=1, max_length=500)
    scientific_context_summary: str = Field(min_length=1, max_length=1500)
    narrative_arc: list[NarrativeAct]
    scenes: list[ScenePlan] = Field(min_length=5, max_length=10)
    epilogue: str = Field(min_length=1, max_length=600)
    external_research_required: bool = False
    research_questions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def research_gate_is_consistent(self):
        if self.external_research_required and not self.research_questions:
            raise ValueError(
                "external_research_required=true requires research_questions"
            )
        return self


class AstronomyVideoPlan(AstronomyVideoPlanDraft):
    context_hash: str
    generation_origin: GenerationOrigin
    model_used: str
    repair_attempted: bool
    total_duration_seconds: int
    requires_human_review: bool = True
    approved_for_publication: bool = False
    generated_at_utc: datetime


class AstronomyDirectorRequest(StrictDirectorModel):
    subject: str = Field(min_length=3, max_length=300)
    astronomy: AstronomyContextRequest
    target_duration_seconds: int = Field(default=60, ge=30, le=180)
    scene_count: int = Field(default=7, ge=5, le=10)
    backend: DirectorBackend = DirectorBackend.OLLAMA_LOCAL
    model: str | None = None
    temperature: float = Field(default=0.15, ge=0.0, le=0.8)
    allow_fallback: bool = True


class AstronomyDirectorHealth(StrictDirectorModel):
    status: str
    backend: DirectorBackend
    ollama_reachable: bool
    available_models: list[str]
    preferred_model: str | None
    network_scope: Literal["loopback_only"]
    thinking_disabled_for_structured_output: bool
    structured_output_schema_enabled: bool
    paid_api_used: bool


class AstronomyDirectorHealthResponse(BaseResponse):
    data: AstronomyDirectorHealth


class AstronomyDirectorPlanResponse(BaseResponse):
    data: AstronomyVideoPlan
