from app.models.analytics_brain import AnalyticsPlatform
from app.models.metric_normalizer import (
    CanonicalMetric,
    MetricNormalizerPlan,
    NormalizationStatus,
    NormalizedMetricObservation,
)
from app.models.analytics_brain import NativeMetricObservation
from app.models.performance_signals import PerformanceSignalsRequest, PerformanceSignalStatus
from app.services.performance_signals import build_performance_signals


def normalized(content_id, metric, value):
    source = NativeMetricObservation.model_construct(
        platform=AnalyticsPlatform.YOUTUBE,
        content_id=content_id,
        value=value,
    )
    return NormalizedMetricObservation.model_construct(
        source=source,
        canonical_metric=metric,
        normalization_status=NormalizationStatus.NORMALIZED_VERIFIED,
    )


def plan(items):
    return MetricNormalizerPlan.model_construct(
        observations=items,
        metric_normalizer_hash="norm",
    )


def test_empty_waits():
    result = build_performance_signals(
        PerformanceSignalsRequest.model_construct(metrics=plan([]), minimum_cohort_size=5)
    )
    assert result.status == PerformanceSignalStatus.WAITING_FOR_ANALYTICS_DATA


def test_small_cohort_is_not_ranked():
    items = [normalized("a", CanonicalMetric.VIEW_COUNT, 10)]
    result = build_performance_signals(
        PerformanceSignalsRequest.model_construct(metrics=plan(items), minimum_cohort_size=5)
    )
    assert result.status == PerformanceSignalStatus.INSUFFICIENT_COHORT
    assert result.signals[0].view_percentile_within_cohort is None


def test_ready_cohort_gets_within_platform_percentiles():
    items = [
        normalized(str(i), CanonicalMetric.VIEW_COUNT, i * 10)
        for i in range(1, 6)
    ]
    result = build_performance_signals(
        PerformanceSignalsRequest.model_construct(metrics=plan(items), minimum_cohort_size=5)
    )
    assert result.status == PerformanceSignalStatus.COHORT_SIGNALS_READY
    assert result.ready_signal_count == 5


def test_no_composite_or_causal_claim():
    items = [normalized("a", CanonicalMetric.VIEW_COUNT, 10)]
    result = build_performance_signals(
        PerformanceSignalsRequest.model_construct(metrics=plan(items), minimum_cohort_size=5)
    )
    assert result.composite_score_enabled is False
    assert result.causal_claims is False
    assert all(item.composite_score is None for item in result.signals)


def test_no_cross_platform_ranking():
    result = build_performance_signals(
        PerformanceSignalsRequest.model_construct(metrics=plan([]), minimum_cohort_size=5)
    )
    assert result.cross_platform_ranking is False
