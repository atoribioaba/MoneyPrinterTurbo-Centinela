from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from app.models.observation import AstronomyConditionsSnapshot, EvidenceKind
from app.services.centinela.http_json import fetch_json_https


SEVEN_TIMER_ASTRO_ENDPOINT = "https://www.7timer.info/bin/api.pl"
SEVEN_TIMER_HOST = "www.7timer.info"
SEVEN_TIMER_SOURCE_URL = "https://7timer.info/doc.php?lang=en"
SEVEN_TIMER_TERMS_CLASSIFICATION = "FREE_TO_USE_TERMS_NON_SPDX"
SEVEN_TIMER_TERMS_NOTE = (
    "7Timer! states the service is provided as-is and may be used for software "
    "without asking permission. This is a provider term, not an SPDX licence."
)

_SEEING_BOUNDS_ARCSEC: dict[int, tuple[float | None, float | None]] = {
    1: (None, 0.5),
    2: (0.5, 0.75),
    3: (0.75, 1.0),
    4: (1.0, 1.25),
    5: (1.25, 1.5),
    6: (1.5, 2.0),
    7: (2.0, 2.5),
    8: (2.5, None),
}

_TRANSPARENCY_EXTINCTION_BOUNDS: dict[
    int, tuple[float | None, float | None]
] = {
    1: (None, 0.3),
    2: (0.3, 0.4),
    3: (0.4, 0.5),
    4: (0.5, 0.6),
    5: (0.6, 0.7),
    6: (0.7, 0.85),
    7: (0.85, 1.0),
    8: (1.0, None),
}


def build_7timer_astro_url(*, latitude: float, longitude: float) -> str:
    """Build a machine-readable 7Timer ASTRO JSON request URL."""
    latitude = float(latitude)
    longitude = float(longitude)
    if not -90.0 <= latitude <= 90.0:
        raise ValueError("latitude must be between -90 and 90 degrees")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError("longitude must be between -180 and 180 degrees")

    query = urlencode(
        {
            "lon": f"{longitude:.3f}",
            "lat": f"{latitude:.3f}",
            "product": "astro",
            "output": "json",
        }
    )
    return f"{SEVEN_TIMER_ASTRO_ENDPOINT}?{query}"


def _payload_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _parse_init_utc(value: Any) -> datetime:
    text = str(value or "").strip()
    if len(text) != 10 or not text.isdigit():
        raise ValueError("7Timer init must use YYYYMMDDHH")
    return datetime.strptime(text, "%Y%m%d%H").replace(tzinfo=UTC)


def _category(value: Any, mapping: dict[int, Any]) -> int | None:
    try:
        category = int(value)
    except (TypeError, ValueError):
        return None
    return category if category in mapping else None


def parse_7timer_astro_payload(
    payload: dict[str, Any],
    *,
    retrieved_at: datetime,
) -> list[AstronomyConditionsSnapshot]:
    """Parse 7Timer ASTRO JSON while preserving source-published bins.

    No midpoint or exact-value fabrication is performed. Seeing remains an
    arcsecond interval and atmospheric transparency remains an extinction
    interval in magnitudes per airmass. The exact canonical response hash is
    embedded in each source identity.
    """
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")
    if str(payload.get("product", "")).strip().lower() != "astro":
        raise ValueError("7Timer payload product must be astro")

    init_at = _parse_init_utc(payload.get("init"))
    payload_hash = _payload_sha256(payload)
    dataseries = payload.get("dataseries")
    if not isinstance(dataseries, list):
        raise ValueError("7Timer dataseries must be a list")

    snapshots: list[AstronomyConditionsSnapshot] = []
    for row in dataseries:
        if not isinstance(row, dict):
            continue
        try:
            timepoint_hours = int(row.get("timepoint"))
        except (TypeError, ValueError):
            continue
        if timepoint_hours < 0:
            continue

        seeing_category = _category(row.get("seeing"), _SEEING_BOUNDS_ARCSEC)
        transparency_category = _category(
            row.get("transparency"), _TRANSPARENCY_EXTINCTION_BOUNDS
        )
        if seeing_category is None and transparency_category is None:
            continue

        seeing_min = seeing_max = None
        if seeing_category is not None:
            seeing_min, seeing_max = _SEEING_BOUNDS_ARCSEC[seeing_category]

        extinction_min = extinction_max = None
        if transparency_category is not None:
            extinction_min, extinction_max = _TRANSPARENCY_EXTINCTION_BOUNDS[
                transparency_category
            ]

        valid_at = init_at + timedelta(hours=timepoint_hours)
        source_id = (
            f"7timer:astro:{payload_hash}:tp={timepoint_hours}:"
            f"valid={valid_at.isoformat()}"
        )
        snapshots.append(
            AstronomyConditionsSnapshot(
                source_id=source_id,
                valid_at=valid_at,
                retrieved_at=retrieved_at,
                evidence_kind=EvidenceKind.FORECAST,
                model_name="7Timer! ASTRO categorical forecast",
                model_run_at=init_at,
                seeing_arcsec_min=seeing_min,
                seeing_arcsec_max=seeing_max,
                transparency_extinction_mag_per_airmass_min=extinction_min,
                transparency_extinction_mag_per_airmass_max=extinction_max,
                provider_seeing_category=seeing_category,
                provider_transparency_category=transparency_category,
            )
        )

    return snapshots


def fetch_7timer_astro_snapshots(
    *,
    latitude: float,
    longitude: float,
    retrieved_at: datetime | None = None,
    timeout_seconds: float = 15.0,
    opener=None,
) -> list[AstronomyConditionsSnapshot]:
    """Fetch 7Timer ASTRO only on an explicit call; no automatic retry is used."""
    retrieved = retrieved_at or datetime.now(UTC)
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")
    url = build_7timer_astro_url(latitude=latitude, longitude=longitude)
    fetch_kwargs = {
        "allowed_hosts": {SEVEN_TIMER_HOST},
        "timeout_seconds": timeout_seconds,
    }
    if opener is not None:
        fetch_kwargs["opener"] = opener
    payload = fetch_json_https(url, **fetch_kwargs)
    return parse_7timer_astro_payload(payload, retrieved_at=retrieved)
