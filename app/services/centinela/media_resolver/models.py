from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.astromedia import MediaType, Provider, Rights


MEDIA_RESOLVER_VERSION = "media-resolver-v0.1"


class StrictResolverModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class MediaResolverRequest(StrictResolverModel):
    refresh_catalog: bool = False
    catalog_root: str = r"D:\ASTRONOMÍA\Medios"
    import_task_artifacts: bool = True
    semantic_evidence: bool = False
    analyze_selected_focal: bool = True
    min_relevance_score: float = Field(default=6.0, ge=0.0, le=1000.0)
    max_alternatives: int = Field(default=3, ge=0, le=20)
    max_candidates_per_scene: int = Field(default=12, ge=1, le=100)
    avoid_reuse: bool = True
    allow_ai_last_resort: bool = True
    publication_eligible_only: bool = False

    @model_validator(mode="after")
    def validate_catalog_root(self):
        if not self.catalog_root.strip():
            raise ValueError("catalog_root must not be empty")
        return self


class SemanticEvidence(StrictResolverModel):
    requested: bool
    analyzed: bool
    method: str
    error: str = ""
    queries: list[str] = Field(default_factory=list)
    ordered_media_ids: list[str] = Field(default_factory=list)
    matches: list[dict[str, Any]] = Field(default_factory=list)


class FocalEvidence(StrictResolverModel):
    applicable: bool
    media_id: str | None = None
    focal_x: float = Field(default=0.5, ge=0.0, le=1.0)
    focal_y: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    method: str
    error: str = ""


class NormalizedMediaCandidate(StrictResolverModel):
    source_id: str = "astromedia_catalog"
    media_id: str
    local_path: str
    media_type: MediaType
    provider: Provider
    rights_status: Rights
    publication_eligible: bool
    renderable: bool
    title: str = ""
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    astronomy_objects: list[str] = Field(default_factory=list)
    source_url: str | None = None
    license_name: str | None = None
    license_url: str | None = None
    attribution: str | None = None
    attribution_required: bool = False
    scientific_status: str
    content_sha256: str | None = None
    lexical_score: float = 0.0
    lexical_reasons: list[str] = Field(default_factory=list)
    semantic_rank: int | None = Field(default=None, ge=1)


class SceneMediaEvidence(StrictResolverModel):
    scene_number: int = Field(ge=1)
    scene_key: str
    query: str
    candidate_count: int = Field(ge=0)
    candidates: list[NormalizedMediaCandidate] = Field(default_factory=list)
    semantic: SemanticEvidence
    selection_status: str
    selected_media_id: str | None = None
    selected_provider: Provider | None = None
    selected_rights_status: Rights | None = None
    selected_publication_eligible: bool | None = None
    focal: FocalEvidence


class ResolverGuardrails(StrictResolverModel):
    material_selector_is_final_authority: bool = True
    semantic_matcher_is_secondary_evidence_only: bool = True
    smartfocal_runs_after_selection_only: bool = True
    restricted_media_rejected_by_selector: bool = True
    irrelevant_broll_fallback: bool = False
    ai_generation_triggered: bool = False
    wangp_triggered: bool = False
    auto_publication: bool = False
    network_discovery_default: bool = False


class MediaResolutionReport(StrictResolverModel):
    version: str = MEDIA_RESOLVER_VERSION
    subject: str
    source_plan_context_hash: str
    selector_version: str
    catalog_item_count: int = Field(ge=0)
    catalog_provider_counts: dict[str, int] = Field(default_factory=dict)
    catalog_refreshed: bool
    catalog_index_report: dict[str, Any] | None = None
    scene_count: int = Field(ge=1)
    selected_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    rights_review_count: int = Field(ge=0)
    review_required: bool
    publication_ready: bool
    scenes: list[SceneMediaEvidence]
    guardrails: ResolverGuardrails = Field(default_factory=ResolverGuardrails)
    generated_at_utc: datetime

    @model_validator(mode="after")
    def validate_counts(self):
        if self.scene_count != len(self.scenes):
            raise ValueError("scene_count must equal scenes length")
        if self.selected_count + self.unresolved_count != self.scene_count:
            raise ValueError("selected_count + unresolved_count must equal scene_count")
        return self


class MediaResolveOutcome(StrictResolverModel):
    selection: dict[str, Any]
    report: MediaResolutionReport
