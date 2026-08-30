from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Any

from app.models.analytics_brain import (
    AnalyticsBrainRequest,
    AnalyticsPlatform,
    AnalyticsSemanticConfidence,
    AnalyticsSourceType,
    MetricValueType,
    NativeMetricObservation,
)
from app.models.analytics_import_adapter import (
    ANALYTICS_IMPORT_ADAPTER_VERSION,
    AnalyticsImportFormat,
    AnalyticsImportPlan,
    AnalyticsImportRequest,
    AnalyticsImportStatus,
)


class AnalyticsImportError(RuntimeError):
    pass


def _hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(payload).hexdigest().upper()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "y",
        "si",
        "sí",
    }


def _none(value: Any) -> Any | None:
    return None if value is None or str(value).strip() == "" else value


def _utc_datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observed_at_utc must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def _rows(request: AnalyticsImportRequest) -> list[dict[str, Any]]:
    text = request.payload_text.strip()
    if not text:
        return []

    if request.format == AnalyticsImportFormat.CSV:
        return list(csv.DictReader(io.StringIO(text)))

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnalyticsImportError(f"invalid JSON: {exc}") from exc

    if isinstance(raw, dict):
        raw = raw.get("observations", raw.get("rows"))
    if not isinstance(raw, list):
        raise AnalyticsImportError(
            "JSON must be an array or contain observations/rows array"
        )
    if not all(isinstance(item, dict) for item in raw):
        raise AnalyticsImportError("all import rows must be objects")
    return raw


def build_analytics_import(request: AnalyticsImportRequest) -> AnalyticsImportPlan:
    rows = _rows(request)
    observations: list[NativeMetricObservation] = []

    for index, row in enumerate(rows, 1):
        try:
            platform = row.get("platform") or (
                request.default_platform.value if request.default_platform else None
            )
            if not platform:
                raise ValueError("platform is required")

            source_type = row.get("source_type") or request.default_source_type.value
            confidence = (
                row.get("semantic_confidence")
                or request.default_semantic_confidence.value
            )

            observations.append(
                NativeMetricObservation(
                    platform=AnalyticsPlatform(str(platform).upper()),
                    content_id=str(row["content_id"]).strip(),
                    native_metric_name=str(row["native_metric_name"]).strip(),
                    value=float(row["value"]),
                    value_type=MetricValueType(str(row["value_type"]).upper()),
                    observed_at_utc=_utc_datetime(row["observed_at_utc"]),
                    source_type=AnalyticsSourceType(str(source_type).upper()),
                    source_ref=_none(row.get("source_ref")),
                    semantic_confidence=AnalyticsSemanticConfidence(
                        str(confidence).upper()
                    ),
                    position_ratio=(
                        float(row["position_ratio"])
                        if _none(row.get("position_ratio")) is not None
                        else None
                    ),
                    estimated=_bool(row.get("estimated", False)),
                )
            )
        except Exception as exc:
            raise AnalyticsImportError(f"row {index}: {exc}") from exc

    analytics_request = AnalyticsBrainRequest(observations=observations)
    status = (
        AnalyticsImportStatus.IMPORT_READY
        if observations
        else AnalyticsImportStatus.WAITING_FOR_IMPORT_DATA
    )
    stable = {
        "version": ANALYTICS_IMPORT_ADAPTER_VERSION,
        "format": request.format.value,
        "observations": [item.model_dump(mode="json") for item in observations],
    }

    return AnalyticsImportPlan(
        status=status,
        row_count=len(rows),
        observation_count=len(observations),
        observations=observations,
        analytics_request=analytics_request,
        analytics_import_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
