from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.astronomy import ScientificStatus, SourceReference
from app.models.astronomy_director import GroundingFact, NarrativeAct

WRITER_ROOM_VERSION = "writer-room-v0.1"
FACT_LOCK_VERSION = "fact-lock-v0.1"

WRITER_ROOM_LOGICAL_STAGES = (
    "FACT_LOCK",
    "CREATIVE_THESIS",
    "STORY_ARCHITECT",
    "HOOK_ROOM",
    "DRAFT",
    "SCIENCE_CRITIC",
    "RETENTION_CRITIC",
    "VISUAL_CRITIC",
    "REWRITE",
    "ADVERSARIAL_READER",
    "FINAL_POLISH",
    "SOCIAL_COMPRESSION",
)

_CONTEXT_HASH_RE = re.compile(r"^[0-9A-F]{64}$")


class StrictWriterModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def compute_fact_lock_context_hash(
    facts: list[GroundingFact],
    source_ids: list[str],
) -> str:
    """Return the canonical semantic hash used by every FactLock producer."""
    payload = {
        "facts": [item.model_dump(mode="json") for item in facts],
        "source_ids": list(source_ids),
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


class WriterRoomRequest(StrictWriterModel):
    subject: str = Field(min_length=3, max_length=512)
    language: str = Field(default="es-ES", min_length=2, max_length=32)
    audience: str = Field(
        default="divulgación astronómica general",
        min_length=3,
        max_length=200,
    )
    target_duration_seconds: int = Field(default=60, ge=30, le=180)
    model: str | None = Field(default=None, max_length=200)
    temperature: float = Field(default=0.25, ge=0.0, le=0.7)


class FactLock(StrictWriterModel):
    version: Literal["fact-lock-v0.1"] = FACT_LOCK_VERSION
    subject: str = Field(min_length=3, max_length=512)
    research_mode: Literal["GENERIC_GEOCENTRIC", "OBSERVATION_CONTEXT"]
    context_hash: str = Field(min_length=64, max_length=64)
    facts: list[GroundingFact] = Field(min_length=1, max_length=256)
    sources: list[SourceReference] = Field(default_factory=list, max_length=128)
    source_ids: list[str] = Field(default_factory=list, max_length=128)
    scope_note: str = Field(min_length=1, max_length=4000)
    location_assumed: bool = False
    moment_basis: str = Field(min_length=1, max_length=200)
    primary_source_verification_required_for_publication: bool = True
    generated_at_utc: datetime

    @field_validator("source_ids")
    @classmethod
    def unique_source_ids(cls, value: list[str]) -> list[str]:
        return sorted({item.strip() for item in value if item.strip()})

    @model_validator(mode="after")
    def validate_semantic_integrity(self):
        fact_ids = [fact.fact_id.strip() for fact in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("FactLock fact_id values must be unique")

        canonical_source_ids = sorted(
            {
                source_id.strip()
                for fact in self.facts
                for source_id in fact.source_ids
                if source_id.strip()
            }
        )
        if self.source_ids != canonical_source_ids:
            raise ValueError(
                "FactLock source_ids must equal the canonical union of fact source_ids"
            )

        source_reference_ids = [source.source_id.strip() for source in self.sources]
        if len(source_reference_ids) != len(set(source_reference_ids)):
            raise ValueError("FactLock SourceReference source_id values must be unique")
        missing_sources = sorted(set(self.source_ids) - set(source_reference_ids))
        if missing_sources:
            raise ValueError(
                "FactLock source_ids missing SourceReference entries: "
                + ", ".join(missing_sources)
            )

        if not _CONTEXT_HASH_RE.fullmatch(self.context_hash):
            raise ValueError("FactLock context_hash must be uppercase SHA-256 hex")
        expected_hash = compute_fact_lock_context_hash(self.facts, self.source_ids)
        if self.context_hash != expected_hash:
            raise ValueError("FactLock context_hash does not match facts/source_ids")
        return self


class ScriptClaim(StrictWriterModel):
    statement: str = Field(min_length=1, max_length=600)
    fact_ids: list[str] = Field(min_length=1, max_length=8)
    scientific_status: ScientificStatus

    @field_validator("fact_ids")
    @classmethod
    def unique_fact_ids(cls, value: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            item = item.strip()
            if item and item not in seen:
                seen.add(item)
                result.append(item)
        if not result:
            raise ValueError("at least one fact_id is required")
        return result


class StoryBeat(StrictWriterModel):
    act: NarrativeAct
    intent: str = Field(min_length=1, max_length=500)
    tension: str = Field(min_length=1, max_length=500)
    visual_intent: str = Field(min_length=1, max_length=700)


class DraftPacket(StrictWriterModel):
    creative_thesis: str = Field(min_length=20, max_length=800)
    story_arc: list[StoryBeat] = Field(min_length=5, max_length=5)
    hook_candidates: list[str] = Field(min_length=3, max_length=3)
    selected_hook: str = Field(min_length=5, max_length=600)
    draft_narration: str = Field(min_length=80, max_length=7000)
    claims: list[ScriptClaim] = Field(min_length=1, max_length=40)
    visual_beats: list[str] = Field(min_length=5, max_length=12)

    @model_validator(mode="after")
    def canonical_story_arc(self):
        acts = [item.act for item in self.story_arc]
        if acts != list(NarrativeAct):
            raise ValueError(
                "story_arc must be introduction, development, climax, "
                "resolution, epilogue"
            )
        return self


class CriticIssue(StrictWriterModel):
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    note: str = Field(min_length=1, max_length=700)
    fix: str = Field(min_length=1, max_length=700)
    claim_index: int | None = Field(default=None, ge=0, le=39)


class CritiqueBundle(StrictWriterModel):
    science_score: float = Field(ge=0.0, le=10.0)
    retention_score: float = Field(ge=0.0, le=10.0)
    visual_score: float = Field(ge=0.0, le=10.0)
    adversarial_score: float = Field(ge=0.0, le=10.0)
    science_issues: list[CriticIssue] = Field(default_factory=list, max_length=20)
    retention_issues: list[CriticIssue] = Field(default_factory=list, max_length=20)
    visual_issues: list[CriticIssue] = Field(default_factory=list, max_length=20)
    adversarial_issues: list[CriticIssue] = Field(default_factory=list, max_length=20)


class PronunciationEntry(StrictWriterModel):
    written: str = Field(min_length=1, max_length=120)
    spoken_es: str = Field(min_length=1, max_length=180)


class FinalScriptSegment(StrictWriterModel):
    act: NarrativeAct
    narration: str = Field(min_length=10, max_length=1800)
    visual_intent: str = Field(min_length=10, max_length=1000)
    claim_indices: list[int] = Field(default_factory=list, max_length=16)
    estimated_seconds: int = Field(ge=2, le=60)

    @field_validator("claim_indices")
    @classmethod
    def unique_claim_indices(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))


class FinalScriptCandidate(StrictWriterModel):
    hook: str = Field(min_length=5, max_length=600)
    narration: str = Field(min_length=80, max_length=7000)
    segments: list[FinalScriptSegment] = Field(min_length=5, max_length=5)
    claims: list[ScriptClaim] = Field(min_length=1, max_length=40)
    pronunciation_map: list[PronunciationEntry] = Field(
        default_factory=list,
        max_length=20,
    )
    social_30s: str = Field(min_length=40, max_length=3500)
    social_15s: str = Field(min_length=20, max_length=1800)
    closing_line: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_segments(self):
        acts = [item.act for item in self.segments]
        if acts != list(NarrativeAct):
            raise ValueError(
                "segments must be introduction, development, climax, "
                "resolution, epilogue"
            )
        claim_count = len(self.claims)
        for segment in self.segments:
            bad = [
                index
                for index in segment.claim_indices
                if index < 0 or index >= claim_count
            ]
            if bad:
                raise ValueError(
                    f"segment references invalid claim indices: {bad}"
                )
        return self


class FinalScript(StrictWriterModel):
    version: Literal["writer-room-v0.1"] = WRITER_ROOM_VERSION
    subject: str = Field(min_length=3, max_length=512)
    language: str = Field(min_length=2, max_length=32)
    audience: str = Field(min_length=3, max_length=200)
    target_duration_seconds: int = Field(ge=30, le=180)
    creative_thesis: str = Field(min_length=20, max_length=800)
    hook: str = Field(min_length=5, max_length=600)
    narration: str = Field(min_length=80, max_length=7000)
    segments: list[FinalScriptSegment] = Field(min_length=5, max_length=5)
    claims: list[ScriptClaim] = Field(min_length=1, max_length=40)
    pronunciation_map: list[PronunciationEntry] = Field(
        default_factory=list,
        max_length=20,
    )
    social_30s: str = Field(min_length=40, max_length=3500)
    social_15s: str = Field(min_length=20, max_length=1800)
    closing_line: str = Field(min_length=3, max_length=500)
    fact_lock_hash: str = Field(min_length=64, max_length=64)
    model_used: str = Field(min_length=1, max_length=200)
    logical_stages: list[str] = Field(min_length=12, max_length=12)
    inference_passes: int = Field(default=3, ge=3, le=3)
    llm_request_count: int = Field(ge=3, le=6)
    source_ids: list[str] = Field(default_factory=list, max_length=128)
    scientifically_grounded: bool = True
    requires_human_review: bool = True
    approved_for_publication: bool = False
    primary_source_verification_required_for_publication: bool = True
    generated_at_utc: datetime
    content_hash: str = Field(min_length=64, max_length=64)


class WriterRoomReport(StrictWriterModel):
    version: Literal["writer-room-v0.1"] = WRITER_ROOM_VERSION
    subject: str = Field(min_length=3, max_length=512)
    model_used: str = Field(min_length=1, max_length=200)
    draft: DraftPacket
    critique: CritiqueBundle
    final_script_hash: str = Field(min_length=64, max_length=64)
    logical_stages: list[str] = Field(min_length=12, max_length=12)
    inference_passes: int = Field(default=3, ge=3, le=3)
    llm_request_count: int = Field(ge=3, le=6)
    generated_at_utc: datetime
