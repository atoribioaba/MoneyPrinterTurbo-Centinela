from __future__ import annotations

import math
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
class CanonicalScientificQuantity:
    """Source-aware scientific quantity used for deterministic reconciliation."""

    subject: str
    quantity: str
    epoch: str
    observer: str
    unit: str
    frame: str
    value: float
    uncertainty: float | None
    display_precision: int | None
    source: str
    provenance: dict[str, Any]

    def __post_init__(self) -> None:
        for name in (
            "subject",
            "quantity",
            "epoch",
            "observer",
            "unit",
            "frame",
            "source",
        ):
            raw = getattr(self, name)
            if not isinstance(raw, str) or not raw.strip():
                raise ResearchDataError(f"{name} must be a non-empty string")
            object.__setattr__(self, name, raw.strip())

        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ResearchDataError("value must be a finite number")
        value = float(self.value)
        if not math.isfinite(value):
            raise ResearchDataError("value must be a finite number")
        object.__setattr__(self, "value", value)

        if self.uncertainty is not None:
            if isinstance(self.uncertainty, bool) or not isinstance(
                self.uncertainty, (int, float)
            ):
                raise ResearchDataError(
                    "uncertainty must be a finite non-negative number"
                )
            uncertainty = float(self.uncertainty)
            if not math.isfinite(uncertainty) or uncertainty < 0:
                raise ResearchDataError(
                    "uncertainty must be a finite non-negative number"
                )
            object.__setattr__(self, "uncertainty", uncertainty)

        if self.display_precision is not None:
            if isinstance(self.display_precision, bool) or not isinstance(
                self.display_precision, int
            ):
                raise ResearchDataError(
                    "display_precision must be a non-negative integer"
                )
            if self.display_precision < 0:
                raise ResearchDataError(
                    "display_precision must be a non-negative integer"
                )

        if not isinstance(self.provenance, dict):
            raise ResearchDataError("provenance must be a dictionary")
        object.__setattr__(self, "provenance", dict(self.provenance))

    @classmethod
    def from_research_datum(
        cls,
        datum: ResearchDatum,
        *,
        subject: str,
        quantity: str,
        epoch: str,
        observer: str,
        frame: str,
        uncertainty: float | None = None,
        display_precision: int | None = None,
        source: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> CanonicalScientificQuantity:
        if datum.unit is None or not str(datum.unit).strip():
            raise ResearchDataError(
                "canonical scientific quantity requires an explicit unit"
            )
        try:
            value = float(str(datum.value).strip())
        except (TypeError, ValueError) as exc:
            raise ResearchDataError(
                "research datum value cannot be normalized to a finite number"
            ) from exc
        return cls(
            subject=subject,
            quantity=quantity,
            epoch=epoch,
            observer=observer,
            unit=str(datum.unit),
            frame=frame,
            value=value,
            uncertainty=uncertainty,
            display_precision=display_precision,
            source=source or datum.source_id,
            provenance=dict(provenance or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "quantity": self.quantity,
            "epoch": self.epoch,
            "observer": self.observer,
            "unit": self.unit,
            "frame": self.frame,
            "value": self.value,
            "uncertainty": self.uncertainty,
            "display_precision": self.display_precision,
            "source": self.source,
            "provenance": dict(self.provenance),
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
    canonical_quantity: CanonicalScientificQuantity | None = None

    def as_dict(self) -> dict[str, Any]:
        result = {
            "fact_id": self.fact_id,
            "label_es": self.label_es,
            "value": self.value,
            "unit": self.unit,
            "source_id": self.source_id,
            "verified": self.verified,
            "primary_source_required": self.primary_source_required,
        }
        if self.canonical_quantity is not None:
            result["canonical_quantity"] = self.canonical_quantity.as_dict()
        return result


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
