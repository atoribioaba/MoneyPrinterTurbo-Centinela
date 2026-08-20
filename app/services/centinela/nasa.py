"""NASA Image and Video Library policy helpers for Centinela."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

from app.services.centinela.licensing import (
    LicenseAssessment,
    LicenseDecision,
)
from app.services.centinela.provenance import safe_public_url


NASA_ASSET_HOST = "images-assets.nasa.gov"

NASA_MEDIA_USAGE_GUIDELINES = (
    "NASA Media Usage Guidelines"
)

NASA_MEDIA_USAGE_GUIDELINES_URL = (
    "https://www.nasa.gov/"
    "nasa-brand-center/images-and-media/"
)

NASA_RENDITION_SOFT_CAP_BYTES = (
    1024 * 1024 * 1024
)

NASA_PRIMARY_RENDITIONS = (
    "orig",
    "large",
    "medium",
)

NASA_FALLBACK_RENDITIONS = (
    "medium",
    "large",
    "orig",
    "mobile",
    "preview",
    "small",
)

NASA_VIDEO_SUFFIXES = frozenset(
    {
        ".mp4",
        ".mov",
        ".m4v",
        ".webm",
        ".ogv",
        ".ogg",
    }
)

_RIGHTS_FIELD_TOKENS = (
    "copyright",
    "rights",
    "license",
    "licence",
)

_THIRD_PARTY_TEXT_PATTERNS = (
    re.compile(
        r"\bcopyright\b",
        re.IGNORECASE,
    ),
    re.compile(r"©"),
    re.compile(
        r"\ball rights reserved\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bused with permission\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcourtesy of\s+(?!nasa\b)",
        re.IGNORECASE,
    ),
)


def _text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    try:
        result = int(value)
    except (TypeError, ValueError):
        return None

    if result <= 0:
        return None

    return result


def normalize_nasa_asset_url(
    value: Any,
) -> str:
    """
    Accept only the official NASA asset host.

    The Image and Video Library currently emits HTTP asset URLs.
    Centinela upgrades only this known NASA host to HTTPS.
    """

    raw = _text(value)

    if not raw:
        return ""

    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""

    host = (
        parsed.hostname or ""
    ).lower()

    if host != NASA_ASSET_HOST:
        return ""

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return ""

    normalized = urlunsplit(
        (
            "https",
            parsed.netloc,
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )

    return safe_public_url(normalized)


def nasa_rendition_label(
    value: Any,
) -> str:
    url = normalize_nasa_asset_url(
        value
    )

    if not url:
        return ""

    name = PurePosixPath(
        urlsplit(url).path
    ).name.lower()

    for label in (
        "orig",
        "large",
        "medium",
        "mobile",
        "preview",
        "small",
    ):
        if "~" + label in name:
            return label

    return ""


def nasa_video_suffix(
    value: Any,
) -> str:
    url = normalize_nasa_asset_url(
        value
    )

    if not url:
        return ""

    return PurePosixPath(
        urlsplit(url).path
    ).suffix.lower()


def parse_nasa_duration(
    value: Any,
) -> float | None:
    """
    Parse numeric seconds or NASA/ExifTool H:MM:SS duration strings.
    """

    if isinstance(value, bool):
        return None

    if isinstance(
        value,
        (int, float),
    ):
        result = float(value)

        if result > 0:
            return result

        return None

    raw = _text(value)

    if not raw:
        return None

    try:
        numeric = float(raw)
    except ValueError:
        numeric = None

    if (
        numeric is not None
        and numeric > 0
    ):
        return numeric

    parts = raw.split(":")

    if len(parts) not in {
        2,
        3,
    }:
        return None

    try:
        numbers = [
            float(part)
            for part in parts
        ]
    except ValueError:
        return None

    if len(numbers) == 2:
        hours = 0.0
        minutes, seconds = numbers
    else:
        hours, minutes, seconds = numbers

    if (
        hours < 0
        or minutes < 0
        or seconds < 0
        or minutes >= 60
        or seconds >= 60
    ):
        return None

    total = (
        hours * 3600
        + minutes * 60
        + seconds
    )

    if total <= 0:
        return None

    return total


def _third_party_text_signal(
    value: Any,
) -> bool:
    text = _text(value)

    if not text:
        return False

    return any(
        pattern.search(text)
        for pattern
        in _THIRD_PARTY_TEXT_PATTERNS
    )


def _explicit_rights_evidence(
    metadata: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    source = (
        metadata
        if isinstance(metadata, Mapping)
        else {}
    )

    evidence = []

    for key, value in source.items():
        key_text = str(key)
        lower = key_text.lower()
        rendered = _text(value)

        if not rendered:
            continue

        if any(
            token in lower
            for token
            in _RIGHTS_FIELD_TOKENS
        ):
            evidence.append(
                f"{key_text}={rendered}"
            )

    return tuple(evidence)


def normalize_nasa_rights(
    search_record: Mapping[str, Any] | None,
    metadata: Mapping[str, Any] | None,
    *,
    asset_url: str,
) -> dict[str, Any]:
    """
    Normalize NASA rights/provenance signals without inventing a license.

    AVAIL:Owner is intentionally not interpreted as a copyright holder.
    """

    search = (
        search_record
        if isinstance(
            search_record,
            Mapping,
        )
        else {}
    )

    metadata_map = (
        metadata
        if isinstance(
            metadata,
            Mapping,
        )
        else {}
    )

    normalized_asset_url = (
        normalize_nasa_asset_url(
            asset_url
        )
    )

    rights_evidence = (
        _explicit_rights_evidence(
            metadata_map
        )
    )

    text_signal = any(
        _third_party_text_signal(
            search.get(field)
        )
        for field in (
            "title",
            "description",
        )
    )

    text_signal = (
        text_signal
        or any(
            _third_party_text_signal(
                metadata_map.get(field)
            )
            for field in (
                "AVAIL:Title",
                "AVAIL:Description",
            )
        )
    )

    creator_names = []

    for value in (
        search.get("photographer"),
        search.get(
            "secondary_creator"
        ),
        metadata_map.get(
            "AVAIL:Photographer"
        ),
        metadata_map.get(
            "AVAIL:SecondaryCreator"
        ),
        metadata_map.get(
            "AVAIL:Creator"
        ),
    ):
        name = _text(value)

        if (
            name
            and name not in creator_names
        ):
            creator_names.append(name)

    result: dict[str, Any] = {
        "provider": "nasa",
        "credit": "NASA",
        "attribution": "NASA",
        "attribution_required": True,
        "rights_basis":
            NASA_MEDIA_USAGE_GUIDELINES,
        "rights_url":
            NASA_MEDIA_USAGE_GUIDELINES_URL,
        "third_party_signal": bool(
            rights_evidence
            or text_signal
        ),
        "rights_evidence": list(
            rights_evidence
        ),
    }

    if normalized_asset_url:
        result[
            "file_url"
        ] = normalized_asset_url

    if creator_names:
        result["creator"] = {
            "name": "; ".join(
                creator_names
            )
        }

    return result


def assess_nasa_rights(
    source_info: Mapping[str, Any] | None,
) -> LicenseAssessment:
    """
    Apply Centinela's conservative NASA Media Usage Guidelines gate.
    """

    source = (
        source_info
        if isinstance(
            source_info,
            Mapping,
        )
        else {}
    )

    asset_url = (
        normalize_nasa_asset_url(
            source.get("file_url")
        )
    )

    if not asset_url:
        return LicenseAssessment(
            LicenseDecision.REVIEW,
            "NASA asset is not on the trusted NASA asset host",
        )

    if (
        source.get(
            "third_party_signal"
        )
        is True
    ):
        return LicenseAssessment(
            LicenseDecision.REVIEW,
            "NASA metadata or description contains a third-party rights signal",
        )

    evidence = source.get(
        "rights_evidence"
    )

    if (
        isinstance(
            evidence,
            (list, tuple),
        )
        and evidence
    ):
        return LicenseAssessment(
            LicenseDecision.REVIEW,
            "explicit rights metadata requires manual review",
        )

    return LicenseAssessment(
        LicenseDecision.ACCEPT_WITH_ATTRIBUTION,
        "NASA asset accepted under NASA Media Usage Guidelines with attribution",
    )


def _candidate_record(
    candidate: Mapping[str, Any],
) -> dict[str, Any] | None:
    url = normalize_nasa_asset_url(
        candidate.get("url")
    )

    if not url:
        return None

    suffix = nasa_video_suffix(
        url
    )

    if suffix not in NASA_VIDEO_SUFFIXES:
        return None

    label = (
        _text(
            candidate.get("label")
        ).lower()
        or nasa_rendition_label(
            url
        )
    )

    if label not in {
        "orig",
        "large",
        "medium",
        "mobile",
        "preview",
        "small",
    }:
        return None

    return {
        "label": label,
        "url": url,
        "suffix": suffix,
        "content_length":
            _positive_int(
                candidate.get(
                    "content_length"
                )
            ),
    }


def select_nasa_rendition(
    candidates: Sequence[
        Mapping[str, Any]
    ],
    *,
    soft_cap_bytes: int = (
        NASA_RENDITION_SOFT_CAP_BYTES
    ),
) -> dict[str, Any] | None:
    """
    Choose a practical NASA video rendition.

    For orig/large/medium with known Content-Length:
    - highest data budget at or below soft cap;
    - if all exceed the cap, smallest candidate.

    Unknown-size fallback is conservative to avoid accidentally selecting
    a multi-gigabyte original.
    """

    cap = _positive_int(
        soft_cap_bytes
    )

    if cap is None:
        raise ValueError(
            "soft_cap_bytes must be positive"
        )

    normalized = []

    for candidate in candidates:
        if not isinstance(
            candidate,
            Mapping,
        ):
            continue

        record = _candidate_record(
            candidate
        )

        if record is not None:
            normalized.append(
                record
            )

    if not normalized:
        return None

    primary = [
        item
        for item in normalized
        if item["label"]
        in NASA_PRIMARY_RENDITIONS
    ]

    known_primary = [
        item
        for item in primary
        if item[
            "content_length"
        ]
        is not None
    ]

    under_cap = [
        item
        for item in known_primary
        if item[
            "content_length"
        ]
        <= cap
    ]

    if under_cap:
        return max(
            under_cap,
            key=lambda item: (
                item[
                    "content_length"
                ],
                item["label"],
            ),
        )

    if known_primary:
        return min(
            known_primary,
            key=lambda item: (
                item[
                    "content_length"
                ],
                item["label"],
            ),
        )

    by_label = {}

    for item in normalized:
        by_label.setdefault(
            item["label"],
            item,
        )

    for label in (
        NASA_FALLBACK_RENDITIONS
    ):
        candidate = by_label.get(
            label
        )

        if candidate is not None:
            return candidate

    return None
