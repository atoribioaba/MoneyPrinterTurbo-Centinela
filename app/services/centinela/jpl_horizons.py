from __future__ import annotations

import csv
import hashlib
import re
from datetime import UTC, datetime

from app.models.small_body import (
    HorizonsObserverResult,
    HorizonsQueryPlan,
    SmallBodyEphemerisProvenance,
    SmallBodyObserverRequest,
)


HORIZONS_ENDPOINT = "https://ssd.jpl.nasa.gov/api/horizons.api"
HORIZONS_DOCUMENTATION = "https://ssd-api.jpl.nasa.gov/doc/horizons.html"
HORIZONS_SOURCE_ID = "jpl_horizons"
HORIZONS_DOCUMENTED_API_VERSION = "1.3"
HORIZONS_API_SOURCE = "NASA/JPL Horizons API"


def _quote(value: str) -> str:
    return f"'{value}'"


def build_horizons_observer_query(request: SmallBodyObserverRequest) -> HorizonsQueryPlan:
    """Build a topocentric JPL Horizons observer-table request.

    The query is intentionally planned but not executed here. Network retrieval
    belongs to a source adapter that records the returned bytes and their hash.
    `target_command` is passed to Horizons as the authoritative object selector;
    this module never propagates a comet/asteroid orbit locally.
    """
    moment = request.observed_at.astimezone(UTC)
    site_height_km = request.observer.elevation_m / 1000.0
    site_coord = (
        f"{request.observer.longitude_deg:.8f},"
        f"{request.observer.latitude_deg:.8f},"
        f"{site_height_km:.6f}"
    )
    time_text = moment.strftime("%Y-%m-%d %H:%M:%S")

    params = {
        "format": "json",
        "COMMAND": _quote(request.target_command),
        "OBJ_DATA": _quote("YES"),
        "MAKE_EPHEM": _quote("YES"),
        "EPHEM_TYPE": _quote("OBSERVER"),
        "CENTER": _quote("coord@399"),
        "COORD_TYPE": _quote("GEODETIC"),
        "SITE_COORD": _quote(site_coord),
        "TLIST": _quote(time_text),
        "TLIST_TYPE": _quote("CAL"),
        "TIME_TYPE": _quote("UT"),
        "REF_SYSTEM": _quote("ICRF"),
        "ANG_FORMAT": _quote("DEG"),
        "APPARENT": _quote("AIRLESS"),
        "RANGE_UNITS": _quote("AU"),
        "CSV_FORMAT": _quote("YES"),
        "EXTRA_PREC": _quote("YES"),
        # Apparent RA/DEC, Az/El, airmass/extinction, magnitude/surface
        # brightness, illuminated fraction, angular diameter and sky motion.
        "QUANTITIES": _quote("2,4,8,9,10,13,47"),
    }

    return HorizonsQueryPlan(
        endpoint=HORIZONS_ENDPOINT,
        params=params,
        source_id=request.source_id,
        documentation_url=HORIZONS_DOCUMENTATION,
        source_note=(
            "JPL Horizons observer tables provide perspective-dependent observables; "
            "the returned result must be stored with retrieval time and SHA-256 before "
            "publication use. The SSD API fair-use policy requires non-redundant, "
            "non-concurrent requests and appropriate handling of service limits."
        ),
    )


def _target_name(result_text: str) -> str:
    for line in result_text.splitlines():
        if line.strip().startswith("Target body name:"):
            value = line.split("Target body name:", 1)[1].strip()
            value = value.split("{", 1)[0].strip()
            if value:
                return value
    raise ValueError("Horizons result missing Target body name")


def _trim_trailing_empty(values: list[str]) -> list[str]:
    result = [item.strip() for item in values]
    while result and result[-1] == "":
        result.pop()
    return result


def _single_csv_observer_row(result_text: str) -> dict[str, str]:
    lines = result_text.splitlines()
    try:
        start_index = next(
            index for index, line in enumerate(lines) if line.strip() == "$$SOE"
        )
        end_index = next(
            index
            for index, line in enumerate(lines[start_index + 1 :], start_index + 1)
            if line.strip() == "$$EOE"
        )
    except StopIteration as exc:
        raise ValueError("Horizons result missing $$SOE/$$EOE data markers") from exc

    data_lines = [
        line.strip()
        for line in lines[start_index + 1 : end_index]
        if line.strip()
    ]
    if len(data_lines) != 1:
        raise ValueError(
            "single-TLIST Horizons query must return exactly one observer data row"
        )

    header_line = None
    for line in reversed(lines[:start_index]):
        candidate = line.strip()
        if "," in candidate and not candidate.startswith("*"):
            header_line = candidate
            break
    if header_line is None:
        raise ValueError("Horizons CSV result missing a parseable header row")

    header = _trim_trailing_empty(next(csv.reader([header_line])))
    values = _trim_trailing_empty(next(csv.reader([data_lines[0]])))
    if not header or len(header) != len(values):
        raise ValueError("Horizons CSV header/data column count mismatch")
    if any(not item for item in header):
        raise ValueError("Horizons CSV contains an unlabeled data column")
    if len(header) != len(set(header)):
        raise ValueError("Horizons CSV contains duplicate column labels")
    return dict(zip(header, values, strict=True))


def parse_horizons_observer_response(
    payload: dict,
    request: SmallBodyObserverRequest,
    *,
    retrieved_at_utc: datetime,
    accepted_api_versions: set[str] | None = None,
) -> HorizonsObserverResult:
    """Validate one JSON Horizons observer response and bind it to exact bytes.

    JPL documents that callers must inspect the JSON `signature.version` because
    formats can change. The default therefore accepts only the currently reviewed
    API documentation version; a future version must be deliberately reviewed and
    passed explicitly rather than being accepted silently.
    """
    if retrieved_at_utc.tzinfo is None or retrieved_at_utc.utcoffset() is None:
        raise ValueError("retrieved_at_utc must be timezone-aware")
    if not isinstance(payload, dict):
        raise ValueError("Horizons payload must be a JSON object")
    if payload.get("error"):
        raise ValueError("Horizons API returned an error response")

    signature = payload.get("signature")
    if not isinstance(signature, dict):
        raise ValueError("Horizons payload missing signature object")
    api_source = str(signature.get("source") or "").strip()
    api_version = str(signature.get("version") or "").strip()
    if HORIZONS_API_SOURCE not in api_source:
        raise ValueError("Horizons signature source is not the NASA/JPL Horizons API")
    if not api_version:
        raise ValueError("Horizons signature missing API version")

    allowed_versions = accepted_api_versions or {HORIZONS_DOCUMENTED_API_VERSION}
    if api_version not in allowed_versions:
        raise ValueError(
            f"unreviewed Horizons API version: {api_version}; reviewed={sorted(allowed_versions)}"
        )

    result_text = payload.get("result")
    if not isinstance(result_text, str) or not result_text.strip():
        raise ValueError("Horizons payload missing result text")

    result_sha256 = hashlib.sha256(result_text.encode("utf-8")).hexdigest()
    columns = _single_csv_observer_row(result_text)
    provenance = SmallBodyEphemerisProvenance(
        target_command=request.target_command,
        query_time_utc=request.observed_at.astimezone(UTC),
        retrieved_at_utc=retrieved_at_utc.astimezone(UTC),
        source_id=request.source_id,
        api_version=api_version,
        result_sha256=result_sha256,
    )
    return HorizonsObserverResult(
        target_name=_target_name(result_text),
        columns=columns,
        provenance=provenance,
        api_source=api_source,
    )
