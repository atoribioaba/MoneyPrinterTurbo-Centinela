from datetime import datetime, timezone

from app.models.analytics_brain import (
    AnalyticsBrainPlan,
    AnalyticsPlatform,
    AnalyticsSemanticConfidence,
    AnalyticsSourceType,
    MetricValueType,
    NativeMetricObservation,
)
from app.models.metric_normalizer import (
    CanonicalMetric,
    MetricNormalizerRequest,
    NormalizationStatus,
)
from app.services.metric_normalizer import build_metric_normalizer


def brain(platform, metric):
    obs = NativeMetricObservation(
        platform=platform,
        content_id="x",
        native_metric_name=metric,
        value=10,
        value_type=MetricValueType.COUNT,
        observed_at_utc=datetime(2026, 8, 22, tzinfo=timezone.utc),
        source_type=AnalyticsSourceType.OFFICIAL_API,
        semantic_confidence=AnalyticsSemanticConfidence.VERIFIED_PLATFORM_SEMANTICS,
    )
    return AnalyticsBrainPlan.model_construct(
        observations=[obs],
        analytics_brain_hash="brain",
    )


def test_verified_youtube_mapping():
    result = build_metric_normalizer(
        MetricNormalizerRequest.model_construct(
            analytics=brain(AnalyticsPlatform.YOUTUBE, "views")
        )
    )
    item = result.observations[0]
    assert item.canonical_metric == CanonicalMetric.VIEW_COUNT
    assert item.normalization_status == NormalizationStatus.NORMALIZED_VERIFIED


def test_verified_tiktok_public_mapping():
    result = build_metric_normalizer(
        MetricNormalizerRequest.model_construct(
            analytics=brain(AnalyticsPlatform.TIKTOK, "favorites_count")
        )
    )
    assert result.observations[0].canonical_metric == CanonicalMetric.SAVE_COUNT


def test_unknown_instagram_metric_stays_native():
    result = build_metric_normalizer(
        MetricNormalizerRequest.model_construct(
            analytics=brain(AnalyticsPlatform.INSTAGRAM, "mystery_metric")
        )
    )
    item = result.observations[0]
    assert item.normalization_status == NormalizationStatus.NATIVE_ONLY
    assert item.canonical_metric is None


def test_no_cross_platform_equivalence():
    result = build_metric_normalizer(
        MetricNormalizerRequest.model_construct(
            analytics=brain(AnalyticsPlatform.YOUTUBE, "views")
        )
    )
    assert result.cross_platform_equivalence_assumed is False
    assert all(not item.cross_platform_equivalence_assumed for item in result.observations)


def test_empty_is_waiting():
    empty = AnalyticsBrainPlan.model_construct(observations=[], analytics_brain_hash="empty")
    result = build_metric_normalizer(MetricNormalizerRequest.model_construct(analytics=empty))
    assert result.status == "WAITING_FOR_ANALYTICS_DATA"
