from datetime import datetime, timedelta, timezone

from app.models.analytics_brain import (
    AnalyticsPlatform,
    NativeMetricObservation,
)
from app.models.content_feature_registry import (
    ContentBindingStatus,
    ContentFeatureRegistryPlan,
    ContentFeatureSnapshot,
    ContentFeatureValue,
)
from app.models.metric_normalizer import (
    CanonicalMetric,
    MetricNormalizerPlan,
    NormalizationStatus,
    NormalizedMetricObservation,
)
from app.models.outcome_linker import OutcomeLinkerRequest, OutcomeLinkerStatus
from app.services.outcome_linker import build_outcome_linker


NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def feature_plan(bound=True):
    snapshot = ContentFeatureSnapshot(
        snapshot_id="snap",
        source_plan_context_hash="ctx",
        source_story_graph_hash="graph",
        platform=AnalyticsPlatform.YOUTUBE if bound else None,
        content_id="video-1" if bound else None,
        binding_status=(
            ContentBindingStatus.BOUND_TO_CONTENT
            if bound
            else ContentBindingStatus.WAITING_FOR_CONTENT_BINDING
        ),
        feature_count=1,
        features=[
            ContentFeatureValue(
                feature_name="TOTAL_DURATION_SECONDS",
                value=50,
                unit="seconds",
                provenance=["F3.total_duration_seconds"],
            )
        ],
    )
    return ContentFeatureRegistryPlan.model_construct(
        content_feature_registry_hash="features",
        snapshots=[snapshot],
    )


def metric(observed_at, value):
    source = NativeMetricObservation.model_construct(
        platform=AnalyticsPlatform.YOUTUBE,
        content_id="video-1",
        native_metric_name="views",
        value=value,
        observed_at_utc=observed_at,
    )
    return NormalizedMetricObservation.model_construct(
        source=source,
        canonical_metric=CanonicalMetric.VIEW_COUNT,
        normalization_status=NormalizationStatus.NORMALIZED_VERIFIED,
    )


def metric_plan(items):
    return MetricNormalizerPlan.model_construct(
        observations=items,
        metric_normalizer_hash="metrics",
    )


def test_unbound_feature_waits():
    result = build_outcome_linker(
        OutcomeLinkerRequest.model_construct(
            features=feature_plan(False),
            metrics=metric_plan([metric(NOW, 100)]),
        )
    )
    assert result.status == OutcomeLinkerStatus.WAITING_FOR_BOUND_CONTENT_ANALYTICS


def test_bound_feature_joins_verified_metric():
    result = build_outcome_linker(
        OutcomeLinkerRequest.model_construct(
            features=feature_plan(True),
            metrics=metric_plan([metric(NOW, 100)]),
        )
    )
    assert result.status == OutcomeLinkerStatus.JOINED_OUTCOMES_READY
    assert result.record_count == 1
    assert result.records[0].outcomes[0].value == 100


def test_latest_observation_wins():
    result = build_outcome_linker(
        OutcomeLinkerRequest.model_construct(
            features=feature_plan(True),
            metrics=metric_plan([
                metric(NOW, 100),
                metric(NOW + timedelta(hours=1), 150),
            ]),
        )
    )
    assert result.records[0].outcomes[0].value == 150


def test_no_cross_platform_join():
    result = build_outcome_linker(
        OutcomeLinkerRequest.model_construct(
            features=feature_plan(True),
            metrics=metric_plan([]),
        )
    )
    assert result.cross_platform_join is False


def test_hash_deterministic():
    request = OutcomeLinkerRequest.model_construct(
        features=feature_plan(True),
        metrics=metric_plan([metric(NOW, 100)]),
    )
    assert (
        build_outcome_linker(request).outcome_linker_hash
        == build_outcome_linker(request).outcome_linker_hash
    )
