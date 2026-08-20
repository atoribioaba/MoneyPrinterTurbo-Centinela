"""Wikimedia Commons metadata normalization and conservative license gate."""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import re
from typing import Any, Mapping

from app.services.centinela.licensing import (
    LicenseAssessment,
    LicenseDecision,
)
from app.services.centinela.provenance import safe_public_url


class _PlainTextHTMLParser(HTMLParser):
    """Extract public text while discarding markup and script/style contents."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized = tag.lower()

        if normalized in {"script", "style"}:
            self._ignored_depth += 1
            return

        if self._ignored_depth == 0 and normalized in {
            "br",
            "p",
            "div",
            "li",
            "tr",
        }:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()

        if normalized in {"script", "style"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return

        if self._ignored_depth == 0 and normalized in {
            "p",
            "div",
            "li",
            "tr",
        }:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self.parts.append(data)


def _metadata_value(metadata: Mapping[str, Any], key: str) -> Any:
    value = metadata.get(key)

    if isinstance(value, Mapping) and "value" in value:
        return value.get("value")

    return value


def _plain_text(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, (list, tuple, set)):
        parts = [
            text
            for item in value
            if (text := _plain_text(item))
        ]
        return " / ".join(parts) if parts else None

    if not isinstance(value, str):
        value = str(value)

    parser = _PlainTextHTMLParser()

    try:
        parser.feed(value)
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        text = value

    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

    return text or None


def _boolish(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, int) and value in {0, 1}:
        return bool(value)

    text = _plain_text(value)

    if not text:
        return None

    normalized = text.strip().lower()

    if normalized in {"true", "1", "yes"}:
        return True

    if normalized in {"false", "0", "no"}:
        return False

    return None


def _restrictions(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()

    if isinstance(value, Mapping) and "value" in value:
        value = value.get("value")

    if isinstance(value, (list, tuple, set)):
        items = [
            text
            for item in value
            if (text := _plain_text(item))
        ]
    else:
        text = _plain_text(value)
        if not text:
            return ()

        items = [
            item.strip()
            for item in re.split(r"[|,;]+", text)
            if item.strip()
        ]

    seen: set[str] = set()
    result: list[str] = []

    for item in items:
        key = item.casefold()

        if key not in seen:
            seen.add(key)
            result.append(item)

    return tuple(result)


def normalize_wikimedia_extmetadata(
    extmetadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Convert Commons extmetadata into the existing Centinela provenance schema.

    Wikimedia's extmetadata values can contain HTML. Only explicitly approved
    public fields are extracted here; final persistence still passes through
    centinela.provenance.sanitize_provenance().
    """
    metadata = extmetadata if isinstance(extmetadata, Mapping) else {}

    result: dict[str, Any] = {
        "provider": "wikimedia",
    }

    license_name = (
        _plain_text(_metadata_value(metadata, "LicenseShortName"))
        or _plain_text(_metadata_value(metadata, "UsageTerms"))
    )
    if license_name:
        result["license"] = license_name

    license_url = safe_public_url(
        _plain_text(_metadata_value(metadata, "LicenseUrl"))
    )
    if license_url:
        result["license_url"] = license_url

    artist = _plain_text(_metadata_value(metadata, "Artist"))
    if artist:
        result["creator"] = {"name": artist}

    credit = _plain_text(_metadata_value(metadata, "Credit"))
    if credit:
        result["credit"] = credit

    attribution = _plain_text(
        _metadata_value(metadata, "Attribution")
    )
    if attribution:
        result["attribution"] = attribution

    attribution_required = _boolish(
        _metadata_value(metadata, "AttributionRequired")
    )
    if attribution_required is not None:
        result["attribution_required"] = attribution_required

    non_free = _boolish(
        _metadata_value(metadata, "NonFree")
    )
    if non_free is not None:
        result["non_free"] = non_free

    restrictions = _restrictions(
        _metadata_value(metadata, "Restrictions")
    )
    if restrictions:
        result["restrictions"] = list(restrictions)

    deletion_reason = _plain_text(
        _metadata_value(metadata, "DeletionReason")
    )
    if deletion_reason:
        result["deletion_reason"] = deletion_reason

    copyrighted = _boolish(
        _metadata_value(metadata, "Copyrighted")
    )
    if copyrighted is True:
        result["copyright_status"] = "copyrighted"
    elif copyrighted is False:
        result["copyright_status"] = "public_domain"

    return result


def _normalized_license(value: Any) -> str:
    text = _plain_text(value) or ""
    text = text.upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _looks_multi_licensed(raw_license: str, normalized: str) -> bool:
    raw_upper = raw_license.upper()

    if any(separator in raw_upper for separator in (" / ", ";", " + ")):
        return True

    if " AND " in normalized or " OR " in normalized:
        return True

    families = sum(
        marker in normalized
        for marker in (
            "CC BY",
            "CC0",
            "PUBLIC DOMAIN",
            "GFDL",
            " GPL",
            "LGPL",
            "FREE ART LICENSE",
            "FAL",
        )
    )

    return families > 1


def assess_wikimedia_license(
    source_info: Mapping[str, Any] | None,
) -> LicenseAssessment:
    """Apply Centinela's conservative Wikimedia Commons license policy."""
    source = source_info if isinstance(source_info, Mapping) else {}

    if source.get("non_free") is True:
        return LicenseAssessment(
            LicenseDecision.REJECT,
            "Wikimedia metadata marks the material as non-free",
        )

    restrictions = source.get("restrictions")
    if isinstance(restrictions, (list, tuple)) and restrictions:
        return LicenseAssessment(
            LicenseDecision.REVIEW,
            "reuse restrictions require manual review",
        )

    if source.get("deletion_reason"):
        return LicenseAssessment(
            LicenseDecision.REVIEW,
            "file is marked for deletion or deletion review",
        )

    raw_license = str(source.get("license") or "").strip()
    normalized = _normalized_license(raw_license)

    if not normalized:
        if source.get("copyright_status") == "public_domain":
            decision = LicenseDecision.ACCEPT
        else:
            return LicenseAssessment(
                LicenseDecision.REVIEW,
                "machine-readable license is missing",
            )
    else:
        if _looks_multi_licensed(raw_license, normalized):
            return LicenseAssessment(
                LicenseDecision.REVIEW,
                "multiple or ambiguous licenses require manual review",
            )

        if (
            "PUBLIC DOMAIN" in normalized
            or normalized == "PD"
            or normalized.startswith("PD ")
        ):
            decision = LicenseDecision.ACCEPT

        elif normalized.startswith("CC0") or "CC ZERO" in normalized:
            decision = LicenseDecision.ACCEPT

        elif "CC BY NC" in normalized or "CC BY ND" in normalized:
            return LicenseAssessment(
                LicenseDecision.REJECT,
                "non-commercial or no-derivatives terms are not accepted",
            )

        elif normalized.startswith("CC BY SA"):
            return LicenseAssessment(
                LicenseDecision.REVIEW,
                "share-alike license requires manual workflow review",
            )

        elif normalized.startswith("CC BY"):
            decision = LicenseDecision.ACCEPT_WITH_ATTRIBUTION

        else:
            return LicenseAssessment(
                LicenseDecision.REVIEW,
                f"unrecognized or unsupported license: {raw_license}",
            )

    if (
        decision is LicenseDecision.ACCEPT
        and source.get("attribution_required") is True
    ):
        decision = LicenseDecision.ACCEPT_WITH_ATTRIBUTION

    return LicenseAssessment(
        decision,
        "license accepted by Wikimedia Commons policy",
    )