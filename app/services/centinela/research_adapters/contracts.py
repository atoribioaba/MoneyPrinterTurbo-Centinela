from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ResearchAdapterError(RuntimeError):
    """Base error for C3 astronomy research adapters."""


class ResearchPhaseViolation(ResearchAdapterError):
    """Raised before any transport call outside the RESEARCH phase."""


class ResearchDataError(ResearchAdapterError):
    """Raised when a remote/local source returns unusable or ambiguous data."""


class OptionalRuntimeUnavailable(ResearchAdapterError):
    """Raised when an approved optional local runtime is not installed/configured."""


class ResearchPhase(StrEnum):
    RESEARCH = "RESEARCH"
    SCRIPT = "SCRIPT"
    MEDIA = "MEDIA"
    AUDIO = "AUDIO"
    VIDEO_BASE = "VIDEO_BASE"
    REVIEW = "REVIEW"
    PUBLICATION = "PUBLICATION"


@dataclass(frozen=True, slots=True)
class ResearchContext:
    project_id: str
    phase: ResearchPhase = ResearchPhase.RESEARCH

    def require_research(self) -> None:
        if self.phase is not ResearchPhase.RESEARCH:
            raise ResearchPhaseViolation(
                f"external astronomy research is forbidden during {self.phase.value}"
            )


@dataclass(frozen=True, slots=True)
class ResearchSource:
    source_id: str
    title: str
    provider: str
    url: str
    classification: str = "PRIMARY"
    license: str | None = None
    primary_source: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "provider": self.provider,
            "url": self.url,
            "classification": self.classification,
            "license": self.license,
            "primary_source": self.primary_source,
        }


@dataclass(frozen=True, slots=True)
class ResearchDatum:
    fact_id: str
    label_es: str
    value: Any
    source_id: str
    unit: str | None = None
    verified: bool = True
    primary_source_required: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "label_es": self.label_es,
            "value": self.value,
            "unit": self.unit,
            "source_id": self.source_id,
            "verified": self.verified,
            "primary_source_required": self.primary_source_required,
        }


@dataclass(frozen=True, slots=True)
class ResearchMediaRecord:
    media_id: str
    provider: str
    title: str
    source_page: str
    file_url: str | None = None
    mime: str | None = None
    width: int | None = None
    height: int | None = None
    license: str | None = None
    license_url: str | None = None
    attribution: str | None = None
    attribution_required: bool = False
    rights_decision: str = "review"
    publication_eligible: bool = False
    sha256: str | None = None
    local_file: str | None = None

    def provenance_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "provider": self.provider,
            "asset_id": self.media_id,
            "title": self.title,
            "source_page": self.source_page,
            "rights_basis": self.rights_decision,
        }
        for key in (
            "file_url",
            "mime",
            "license",
            "license_url",
            "attribution",
            "sha256",
            "local_file",
        ):
            value = getattr(self, key)
            if value not in (None, ""):
                result[key] = value
        if self.width and self.height:
            result["rendition"] = {"width": self.width, "height": self.height}
        result["attribution_required"] = bool(self.attribution_required)
        return result

    def license_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "asset_id": self.media_id,
            "license": self.license,
            "license_url": self.license_url,
            "attribution": self.attribution,
            "attribution_required": bool(self.attribution_required),
            "decision": self.rights_decision,
            "publication_eligible": bool(self.publication_eligible),
        }


@dataclass(frozen=True, slots=True)
class ResearchBundle:
    data: tuple[ResearchDatum, ...] = ()
    sources: tuple[ResearchSource, ...] = ()
    media: tuple[ResearchMediaRecord, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "data": [item.as_dict() for item in self.data],
            "sources": [item.as_dict() for item in self.sources],
            "media": [item.provenance_dict() for item in self.media],
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "auto_publication": False,
        }
