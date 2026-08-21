from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astronomy_director import AstronomyVideoPlan
from app.models.astromedia import Provider, Rights


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SelectionStatus(str, Enum):
    SELECTED = "SELECTED"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    SELECTED_AI_RECREATION = "SELECTED_AI_RECREATION"
    NO_ADEQUATE_MEDIA = "NO_ADEQUATE_MEDIA"
    AI_RECREATION_REQUIRED = "AI_RECREATION_REQUIRED"


class MaterialCandidate(StrictModel):
    media_id: str
    local_path: str
    provider: Provider
    rights_status: Rights
    publication_eligible: bool
    relevance_score: float
    total_score: float
    reuse_penalty: float = 0.0
    object_overlap: list[str] = Field(default_factory=list)
    keyword_overlap: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class SceneMaterialSelection(StrictModel):
    scene_number: int
    scene_key: str
    visual_requirement: str
    query: str
    status: SelectionStatus
    selected_media_id: str | None = None
    selected_local_path: str | None = None
    selected_provider: Provider | None = None
    selected_rights_status: Rights | None = None
    selected_publication_eligible: bool | None = None
    selected_source_url: str | None = None
    selected_attribution: str | None = None
    selected_scientific_status: str | None = None
    selected_score: float | None = None
    relevance_score: float | None = None
    manual_override: bool = False
    review_required: bool = True
    reasons: list[str] = Field(default_factory=list)
    alternatives: list[MaterialCandidate] = Field(default_factory=list)


class MaterialSelectionRequest(StrictModel):
    plan: AstronomyVideoPlan
    min_relevance_score: float = Field(default=6.0, ge=0.0, le=1000.0)
    max_alternatives: int = Field(default=3, ge=0, le=20)
    avoid_reuse: bool = True
    allow_ai_last_resort: bool = True
    publication_eligible_only: bool = False


class MaterialSelectionPlan(StrictModel):
    subject: str
    source_plan_context_hash: str
    selector_version: str
    scene_count: int
    selected_count: int
    manual_override_count: int
    unresolved_count: int
    ai_recreation_count: int
    selections: list[SceneMaterialSelection]
    review_required: bool
    publication_ready: bool
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_counts(self):
        if self.scene_count != len(self.selections):
            raise ValueError("scene_count must equal selections length")
        return self
