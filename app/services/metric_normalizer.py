from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.models.analytics_brain import AnalyticsPlatform
from app.models.metric_normalizer import (
    METRIC_NORMALIZER_VERSION,
    CanonicalMetric,
    MetricNormalizerPlan,
    MetricNormalizerRequest,
    NormalizationStatus,
    NormalizedMetricObservation,
)


VERIFIED_MAPPINGS = {
    AnalyticsPlatform.YOUTUBE: {
        "views": CanonicalMetric.VIEW_COUNT,
        "likes": CanonicalMetric.LIKE_COUNT,
        "comments": CanonicalMetric.COMMENT_COUNT,
        "shares": CanonicalMetric.SHARE_COUNT,
        "subscribersGained": CanonicalMetric.FOLLOWERS_GAINED,
        "averageViewDuration": CanonicalMetric.AVG_VIEW_DURATION_SECONDS,
        "averageViewPercentage": CanonicalMetric.AVG_VIEW_PERCENTAGE,
        "audienceWatchRatio": CanonicalMetric.AUDIENCE_WATCH_RATIO,
    },
    AnalyticsPlatform.TIKTOK: {
        "view_count": CanonicalMetric.VIEW_COUNT,
        "like_count": CanonicalMetric.LIKE_COUNT,
        "comment_count": CanonicalMetric.COMMENT_COUNT,
        "share_count": CanonicalMetric.SHARE_COUNT,
        "favorites_count": CanonicalMetric.SAVE_COUNT,
    },
}


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def build_metric_normalizer(request: MetricNormalizerRequest) -> MetricNormalizerPlan:
    results: list[NormalizedMetricObservation] = []

    for source in request.analytics.observations:
        mapping = VERIFIED_MAPPINGS.get(source.platform, {}).get(source.native_metric_name)
        if mapping is None:
            results.append(
                NormalizedMetricObservation(
                    source=source,
                    normalization_status=NormalizationStatus.NATIVE_ONLY,
                    mapping_basis="NO_VERIFIED_MAPPING_IN_F32_V0_1",
                )
            )
        else:
            results.append(
                NormalizedMetricObservation(
                    source=source,
                    canonical_metric=mapping,
                    normalization_status=NormalizationStatus.NORMALIZED_VERIFIED,
                    mapping_basis=f"VERIFIED_PLATFORM_MAPPING:{source.platform.value}:{source.native_metric_name}",
                )
            )

    normalized = sum(
        item.normalization_status == NormalizationStatus.NORMALIZED_VERIFIED
        for item in results
    )
    stable = {
        "version": METRIC_NORMALIZER_VERSION,
        "source_analytics_hash": request.analytics.analytics_brain_hash,
        "observations": [item.model_dump(mode="json") for item in results],
    }

    return MetricNormalizerPlan(
        source_analytics_hash=request.analytics.analytics_brain_hash,
        observation_count=len(results),
        normalized_count=normalized,
        native_only_count=len(results) - normalized,
        observations=results,
        status="NORMALIZATION_COMPLETE" if results else "WAITING_FOR_ANALYTICS_DATA",
        metric_normalizer_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
