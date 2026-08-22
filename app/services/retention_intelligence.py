from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.models.metric_normalizer import CanonicalMetric, NormalizationStatus
from app.models.retention_intelligence import (
    RETENTION_INTELLIGENCE_VERSION,
    RetentionInsight,
    RetentionIntelligencePlan,
    RetentionIntelligenceRequest,
    RetentionStatus,
)


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _nearest(points, target):
    return min(points, key=lambda pair: abs(pair[0] - target))[1]


def build_retention_intelligence(
    request: RetentionIntelligenceRequest,
) -> RetentionIntelligencePlan:
    curves = defaultdict(list)

    for item in request.metrics.observations:
        if (
            item.normalization_status == NormalizationStatus.NORMALIZED_VERIFIED
            and item.canonical_metric == CanonicalMetric.AUDIENCE_WATCH_RATIO
            and item.source.position_ratio is not None
        ):
            key = (item.source.platform, item.source.content_id)
            curves[key].append((item.source.position_ratio, item.source.value))

    insights = []
    for (platform, content_id), points in sorted(
        curves.items(), key=lambda x: (x[0][0].value, x[0][1])
    ):
        points = sorted(points)
        if len(points) < 2:
            continue

        early = [value for position, value in points if position <= 0.10]
        first_10 = round(sum(early) / len(early), 6) if early else None
        midpoint = _nearest(points, 0.5)
        final = points[-1][1]

        largest_drop = 0.0
        largest_drop_position = None
        for previous, current in zip(points, points[1:]):
            drop = previous[1] - current[1]
            if drop > largest_drop:
                largest_drop = drop
                largest_drop_position = current[0]

        insights.append(
            RetentionInsight(
                platform=platform,
                content_id=content_id,
                point_count=len(points),
                first_10_percent_mean=first_10,
                midpoint_ratio=midpoint,
                final_ratio=final,
                largest_drop_position_ratio=largest_drop_position,
                largest_drop_magnitude=round(largest_drop, 6),
            )
        )

    status = (
        RetentionStatus.RETENTION_CURVES_READY
        if insights
        else RetentionStatus.WAITING_FOR_RETENTION_DATA
    )
    stable = {
        "version": RETENTION_INTELLIGENCE_VERSION,
        "source_metric_normalizer_hash": request.metrics.metric_normalizer_hash,
        "insights": [item.model_dump(mode="json") for item in insights],
    }

    return RetentionIntelligencePlan(
        source_metric_normalizer_hash=request.metrics.metric_normalizer_hash,
        status=status,
        curve_count=len(insights),
        insights=insights,
        retention_intelligence_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
