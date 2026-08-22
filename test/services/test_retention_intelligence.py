from app.models.analytics_brain import AnalyticsPlatform, NativeMetricObservation
from app.models.metric_normalizer import (
    CanonicalMetric,
    MetricNormalizerPlan,
    NormalizationStatus,
    NormalizedMetricObservation,
)
from app.models.retention_intelligence import (
    RetentionIntelligenceRequest,
    RetentionStatus,
)
from app.services.retention_intelligence import build_retention_intelligence


def point(position, value):
    source = NativeMetricObservation.model_construct(
        platform=AnalyticsPlatform.YOUTUBE,
        content_id="video",
        position_ratio=position,
        value=value,
    )
    return NormalizedMetricObservation.model_construct(
        source=source,
        canonical_metric=CanonicalMetric.AUDIENCE_WATCH_RATIO,
        normalization_status=NormalizationStatus.NORMALIZED_VERIFIED,
    )


def plan(items):
    return MetricNormalizerPlan.model_construct(
        observations=items,
        metric_normalizer_hash="norm",
    )


def test_empty_waits():
    result = build_retention_intelligence(
        RetentionIntelligenceRequest.model_construct(metrics=plan([]))
    )
    assert result.status == RetentionStatus.WAITING_FOR_RETENTION_DATA


def test_curve_is_described():
    result = build_retention_intelligence(
        RetentionIntelligenceRequest.model_construct(
            metrics=plan([
                point(0.01, 1.0),
                point(0.10, 0.8),
                point(0.50, 0.6),
                point(1.00, 0.4),
            ])
        )
    )
    insight = result.insights[0]
    assert result.status == RetentionStatus.RETENTION_CURVES_READY
    assert insight.point_count == 4
    assert insight.midpoint_ratio == 0.6
    assert insight.final_ratio == 0.4


def test_largest_drop_is_descriptive_only():
    result = build_retention_intelligence(
        RetentionIntelligenceRequest.model_construct(
            metrics=plan([point(0.1, 1.0), point(0.2, 0.5), point(0.5, 0.4)])
        )
    )
    insight = result.insights[0]
    assert insight.largest_drop_position_ratio == 0.2
    assert insight.causal_claim is False
    assert insight.recommendation is None


def test_no_interpolation():
    result = build_retention_intelligence(
        RetentionIntelligenceRequest.model_construct(metrics=plan([]))
    )
    assert result.interpolates_missing_points is False
