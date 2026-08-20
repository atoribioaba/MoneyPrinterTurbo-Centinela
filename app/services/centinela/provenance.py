"""Safe provenance normalization for Centinela Edition.

Only explicitly approved public metadata is persisted. Authentication values,
signed query strings, arbitrary caller fields and absolute local paths are not
copied into provenance records.
"""

import math
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_MIME_PATTERN = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9.+_-]*/[a-zA-Z0-9][a-zA-Z0-9.+_-]*$"
)

_PUBLIC_TEXT_LIMIT = 4096


def safe_public_url(value: Any) -> str | None:
    """Return a public HTTP(S) URL without credentials, query or fragment."""

    if not isinstance(value, str) or not value.strip():
        return None

    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None

    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None

    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            parsed.path,
            "",
            "",
        )
    )


def _safe_text(value: Any, *, limit: int = _PUBLIC_TEXT_LIMIT) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None

    return normalized[:limit]


def _safe_dimension(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return number if number > 0 else None


def _safe_duration(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(number) or number < 0:
        return None

    return number


def sanitize_creator(value: Any) -> dict[str, str] | None:
    """Normalize public creator metadata."""

    if isinstance(value, str):
        name = _safe_text(value)
        return {"name": name} if name else None

    if not isinstance(value, Mapping):
        return None

    creator: dict[str, str] = {}

    creator_id = value.get("id")
    if creator_id not in (None, ""):
        creator["id"] = str(creator_id)[:256]

    name = _safe_text(value.get("name") or value.get("username"))
    if name:
        creator["name"] = name

    profile_page = safe_public_url(
        value.get("profile_page")
        or value.get("profile_url")
        or value.get("url")
    )
    if profile_page:
        creator["profile_page"] = profile_page

    return creator or None


def sanitize_rendition(value: Any) -> dict[str, Any] | None:
    """Normalize rendition metadata without retaining arbitrary fields."""

    if not isinstance(value, Mapping):
        return None

    rendition: dict[str, Any] = {}

    rendition_id = value.get("id")
    if rendition_id not in (None, ""):
        rendition["id"] = str(rendition_id)[:256]

    width = _safe_dimension(value.get("width"))
    height = _safe_dimension(value.get("height"))

    if width is not None:
        rendition["width"] = width
    if height is not None:
        rendition["height"] = height

    return rendition or None


def sanitize_provenance(
    source: Mapping[str, Any] | None,
    *,
    provider: str = "",
    local_path: str = "",
    duration: float | int | None = None,
) -> dict[str, Any]:
    """Create a whitelisted provenance record suitable for task artifacts."""

    source = source if isinstance(source, Mapping) else {}

    provider_value = _safe_text(provider) or _safe_text(source.get("provider"))
    record: dict[str, Any] = {
        "provider": provider_value or "",
    }

    if local_path:
        record["local_file"] = Path(local_path).name

    safe_duration = _safe_duration(
        duration if duration is not None else source.get("duration")
    )
    if safe_duration is not None:
        record["duration"] = safe_duration

    search_term = _safe_text(source.get("search_term"))
    if search_term:
        record["search_term"] = search_term

    title = _safe_text(source.get("title"), limit=1024)
    if title:
        record["title"] = title

    asset_id = source.get("asset_id")
    if asset_id not in (None, ""):
        record["asset_id"] = str(asset_id)[:512]

    source_page = safe_public_url(source.get("source_page"))
    if source_page:
        record["source_page"] = source_page

    # Reserved for stable public media URLs supplied by trusted adapters.
    # Signed/transient URLs must remain in provider-specific secret fields
    # such as signed_url, which are not whitelisted by this sanitizer.
    file_url = safe_public_url(source.get("file_url"))
    if file_url:
        record["file_url"] = file_url

    creator = sanitize_creator(source.get("creator"))
    if creator:
        record["creator"] = creator

    rendition = sanitize_rendition(source.get("rendition"))
    if rendition:
        record["rendition"] = rendition

    for field in (
        "license",
        "credit",
        "attribution",
        "rights_basis",
        "copyright_status",
        "deletion_reason",
    ):
        value = _safe_text(source.get(field))
        if value:
            record[field] = value

    license_url = safe_public_url(source.get("license_url"))
    if license_url:
        record["license_url"] = license_url

    rights_url = safe_public_url(source.get("rights_url"))
    if rights_url:
        record["rights_url"] = rights_url

    for field in (
        "attribution_required",
        "non_free",
    ):
        value = source.get(field)
        if isinstance(value, bool):
            record[field] = value

    restrictions = source.get("restrictions")
    if isinstance(restrictions, str):
        value = _safe_text(restrictions)
        if value:
            record["restrictions"] = [value]
    elif isinstance(restrictions, (list, tuple)):
        clean_restrictions = []
        for item in restrictions:
            clean_item = _safe_text(item)
            if clean_item:
                clean_restrictions.append(clean_item)
        if clean_restrictions:
            record["restrictions"] = clean_restrictions

    mime = _safe_text(source.get("mime"), limit=256)
    if mime and _MIME_PATTERN.fullmatch(mime):
        record["mime"] = mime.lower()

    sha256 = _safe_text(source.get("sha256"), limit=64)
    if sha256 and _SHA256_PATTERN.fullmatch(sha256):
        record["sha256"] = sha256.lower()

    return record
