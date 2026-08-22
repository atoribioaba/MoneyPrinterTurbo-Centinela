from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.models.metric_normalizer import CanonicalMetric, NormalizationStatus
from app.models.performance_signals import (
    PERFORMANCE_SIGNALS_VERSION,
    ContentPerformanceSignal,
    PerformanceSignalsPlan,
    PerformanceSignalsRequest,
    PerformanceSignalStatus,
)


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _percentile(values: list[float], value: float) -> float:
    if len(values) <= 1:
        return 1.0
    lower_or_equal = sum(item <= value for item in values)
    return round((lower_or_equal - 1) / (len(values) - 1), 6)


def build_performance_signals(request: PerformanceSignalsRequest) -> PerformanceSignalsPlan:
    per_content = defaultdict(lambda: defaultdict(float))
    platforms = {}

    for item in request.metrics.observations:
        if item.normalization_status != NormalizationStatus.NORMALIZED_VERIFIED:
            continue
        key = (item.source.platform, item.source.content_id)
        platforms[key] = item.source.platform
        metric = item.canonical_metric
        if metric is not None:
            per_content[key][metric] += item.source.value

    if not per_content:
        status = PerformanceSignalStatus.WAITING_FOR_ANALYTICS_DATA
        signals = []
    else:
        by_platform = defaultdict(list)
        for key in per_content:
            by_platform[key[0]].append(key)

        signals = []
        any_ready = False
        for platform, keys in sorted(by_platform.items(), key=lambda x: x[0].value):
            cohort_size = len(keys)
            views = {
                key: per_content[key].get(CanonicalMetric.VIEW_COUNT)
                for key in keys
            }
            interaction = {}
            for key in keys:
                data = per_content[key]
                parts = [
                    data.get(CanonicalMetric.LIKE_COUNT),
                    data.get(CanonicalMetric.COMMENT_COUNT),
                    data.get(CanonicalMetric.SHARE_COUNT),
                    data.get(CanonicalMetric.SAVE_COUNT),
                ]
                available = [value for value in parts if value is not None]
                interaction[key] = sum(available) if available else None

            view_values = [v for v in views.values() if v is not None]
            rates = {}
            for key in keys:
                v = views[key]
                i = interaction[key]
                rates[key] = (i / v) if v and i is not None else None
            rate_values = [v for v in rates.values() if v is not None]

            for key in sorted(keys, key=lambda x: x[1]):
                ready = cohort_size >= request.minimum_cohort_size
                view_pct = (
                    _percentile(view_values, views[key])
                    if ready and views[key] is not None and len(view_values) >= request.minimum_cohort_size
                    else None
                )
                rate_pct = (
                    _percentile(rate_values, rates[key])
                    if ready and rates[key] is not None and len(rate_values) >= request.minimum_cohort_size
                    else None
                )
                any_ready = any_ready or view_pct is not None or rate_pct is not None
                signals.append(
                    ContentPerformanceSignal(
                        platform=platform,
                        content_id=key[1],
                        cohort_size=cohort_size,
                        view_count=views[key],
                        interaction_count=interaction[key],
                        interaction_rate_per_view=rates[key],
                        view_percentile_within_cohort=view_pct,
                        interaction_rate_percentile_within_cohort=rate_pct,
                    )
                )

        status = (
            PerformanceSignalStatus.COHORT_SIGNALS_READY
            if any_ready
            else PerformanceSignalStatus.INSUFFICIENT_COHORT
        )

    stable = {
        "version": PERFORMANCE_SIGNALS_VERSION,
        "source_metric_normalizer_hash": request.metrics.metric_normalizer_hash,
        "signals": [item.model_dump(mode="json") for item in signals],
        "status": status.value,
    }

    return PerformanceSignalsPlan(
        source_metric_normalizer_hash=request.metrics.metric_normalizer_hash,
        status=status,
        content_count=len(signals),
        ready_signal_count=sum(
            item.view_percentile_within_cohort is not None
            or item.interaction_rate_percentile_within_cohort is not None
            for item in signals
        ),
        signals=signals,
        performance_signals_hash=_hash(stable),
        generated_at_utc=datetime.now(timezone.utc),
    )
