from datetime import datetime, timezone

from app.models.analytics_brain import (
    AnalyticsBrainRequest,
    AnalyticsPlatform,
    AnalyticsSemanticConfidence,
    AnalyticsSourceType,
    MetricValueType,
    NativeMetricObservation,
)
from app.services.analytics_brain import build_analytics_brain


def obs():
    return NativeMetricObservation(
        platform=AnalyticsPlatform.YOUTUBE,
        content_id="video-1",
        native_metric_name="views",
        value=100,
        value_type=MetricValueType.COUNT,
        observed_at_utc=datetime(2026, 8, 22, tzinfo=timezone.utc),
        source_type=AnalyticsSourceType.OFFICIAL_API,
        semantic_confidence=AnalyticsSemanticConfidence.VERIFIED_PLATFORM_SEMANTICS,
    )


def test_empty_is_waiting():
    result = build_analytics_brain(AnalyticsBrainRequest())
    assert result.status == "WAITING_FOR_ANALYTICS_DATA"
    assert result.observation_count == 0


def test_observation_is_preserved():
    result = build_analytics_brain(AnalyticsBrainRequest(observations=[obs()]))
    assert result.status == "READY_FOR_NORMALIZATION"
    assert result.observations[0].native_metric_name == "views"


def test_hash_deterministic_ordering():
    a = obs()
    b = a.model_copy(update={"native_metric_name": "likes", "value": 10})
    p1 = build_analytics_brain(AnalyticsBrainRequest(observations=[a, b]))
    p2 = build_analytics_brain(AnalyticsBrainRequest(observations=[b, a]))
    assert p1.analytics_brain_hash == p2.analytics_brain_hash


def test_no_storage_or_api_side_effects():
    result = build_analytics_brain(AnalyticsBrainRequest())
    assert result.storage_writes == 0
    assert result.api_calls == 0
    assert result.network_calls == 0
    assert result.credentials_required is False


def test_storage_candidates_are_explicit():
    result = build_analytics_brain(AnalyticsBrainRequest())
    assert result.storage_candidate == "SQLite"
    assert result.storage_candidate_license == "Public Domain"
    assert result.alternative_olap_candidate == "DuckDB"
    assert result.alternative_olap_license == "MIT"
