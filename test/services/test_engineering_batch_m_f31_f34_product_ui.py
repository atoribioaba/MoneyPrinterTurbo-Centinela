from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.models.analytics_brain import AnalyticsPlatform
from app.models.analytics_import_adapter import (
    AnalyticsImportFormat,
    AnalyticsImportRequest,
)
from app.models.metric_normalizer import (
    MetricNormalizerRequest,
    NormalizationStatus,
)
from app.models.performance_signals import (
    PerformanceSignalStatus,
    PerformanceSignalsRequest,
)
from app.models.retention_intelligence import (
    RetentionIntelligenceRequest,
    RetentionStatus,
)
from app.services.analytics_brain import build_analytics_brain
from app.services.analytics_import_adapter import build_analytics_import
from app.services.metric_normalizer import build_metric_normalizer
from app.services.performance_signals import build_performance_signals
from app.services.retention_intelligence import build_retention_intelligence


ROOT = Path(__file__).resolve().parents[2]
PAGES = {
    "F31": ROOT / "webui/pages/31_Analytics_Brain.py",
    "F32": ROOT / "webui/pages/32_Metric_Normalizer.py",
    "F33": ROOT / "webui/pages/33_Performance_Signals.py",
    "F34": ROOT / "webui/pages/34_Retention_Intelligence.py",
}


def _source(module: str) -> str:
    return PAGES[module].read_text(encoding="utf-8")


def _tree(module: str) -> ast.AST:
    return ast.parse(_source(module))


def _imports_symbol(tree: ast.AST, module: str, symbol: str) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == module
        and any(alias.name == symbol for alias in node.names)
        for node in ast.walk(tree)
    )


def _calls_symbol(tree: ast.AST, symbol: str) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == symbol
        for node in ast.walk(tree)
    )


def _import_plan(payload: str, platform: AnalyticsPlatform):
    return build_analytics_import(
        AnalyticsImportRequest(
            format=AnalyticsImportFormat.JSON,
            payload_text=payload,
            default_platform=platform,
        )
    )


def test_f31_page_consumes_real_f55_contract_and_calls_real_service():
    tree = _tree("F31")
    assert _imports_symbol(
        tree,
        "app.models.analytics_import_adapter",
        "AnalyticsImportPlan",
    )
    assert _imports_symbol(
        tree,
        "app.services.analytics_brain",
        "build_analytics_brain",
    )
    assert _calls_symbol(tree, "build_analytics_brain")
    source = _source("F31")
    assert ".analytics_request" in source
    assert "AnalyticsImportPlan.model_validate_json" in source


def test_f31_page_does_not_duplicate_f55_import_logic_or_auto_forward():
    source = _source("F31")
    forbidden = (
        "AnalyticsImportRequest",
        "build_analytics_import",
        "csv.DictReader",
        "AnalyticsImportFormat",
        "NativeMetricObservation(",
        "build_metric_normalizer(",
        "build_performance_signals(",
        "build_retention_intelligence(",
    )
    for marker in forbidden:
        assert marker not in source, marker


def test_f32_page_uses_real_normalizer_without_duplicate_mapping_table():
    tree = _tree("F32")
    assert _imports_symbol(
        tree,
        "app.models.analytics_brain",
        "AnalyticsBrainPlan",
    )
    assert _imports_symbol(
        tree,
        "app.models.metric_normalizer",
        "MetricNormalizerRequest",
    )
    assert _imports_symbol(
        tree,
        "app.services.metric_normalizer",
        "build_metric_normalizer",
    )
    assert _calls_symbol(tree, "MetricNormalizerRequest")
    assert _calls_symbol(tree, "build_metric_normalizer")
    source = _source("F32")
    assert "VERIFIED_MAPPINGS" not in source
    assert "CanonicalMetric." not in source


def test_f33_and_f34_pages_use_real_requests_and_services_only():
    f33 = _tree("F33")
    assert _imports_symbol(
        f33,
        "app.models.performance_signals",
        "PerformanceSignalsRequest",
    )
    assert _imports_symbol(
        f33,
        "app.services.performance_signals",
        "build_performance_signals",
    )
    assert _calls_symbol(f33, "PerformanceSignalsRequest")
    assert _calls_symbol(f33, "build_performance_signals")

    f34 = _tree("F34")
    assert _imports_symbol(
        f34,
        "app.models.retention_intelligence",
        "RetentionIntelligenceRequest",
    )
    assert _imports_symbol(
        f34,
        "app.services.retention_intelligence",
        "build_retention_intelligence",
    )
    assert _calls_symbol(f34, "RetentionIntelligenceRequest")
    assert _calls_symbol(f34, "build_retention_intelligence")


def test_batch_m_pages_are_mobile_product_safe_and_fail_closed():
    for module in PAGES:
        source = _source(module)
        assert "st.columns(" not in source
        assert "st.dataframe(" not in source
        assert "st.table(" not in source
        assert "st.json(" not in source
        assert 'st.expander("Detalles técnicos", expanded=False)' in source
        assert "st.code(f\"{type(exc).__name__}: {exc}\", language=None)" in source
        assert "if uploaded is None:" in source
        assert "except Exception as exc:" in source


def test_batch_m_pages_do_not_call_f35_f37_or_policy_paths():
    joined = "\n".join(_source(module) for module in PAGES)
    forbidden = (
        "build_experiment_planner(",
        "build_content_feature_registry(",
        "build_outcome_linker(",
        "build_association_analyzer(",
        "build_policy_candidate(",
        "build_policy_simulator(",
        "build_policy_comparator(",
        "mark_published",
        "authorization_to_publish",
        "sqlite3",
        "requests.",
        "httpx.",
    )
    for marker in forbidden:
        assert marker not in joined, marker


def test_real_f55_to_f31_lineage_preserves_observations_and_side_effects():
    payload = """[
      {
        "content_id": "video-1",
        "native_metric_name": "views",
        "value": 123,
        "value_type": "COUNT",
        "observed_at_utc": "2026-09-05T10:00:00Z"
      }
    ]"""
    imported = _import_plan(payload, AnalyticsPlatform.YOUTUBE)
    result = build_analytics_brain(imported.analytics_request)

    assert result.observation_count == 1
    assert result.observations == imported.analytics_request.observations
    assert result.storage_writes == 0
    assert result.api_calls == 0
    assert result.network_calls == 0
    assert result.auto_publication is False


def test_real_f32_unknown_metric_stays_native_only_without_equivalence():
    payload = """[
      {
        "content_id": "post-1",
        "native_metric_name": "mystery_metric",
        "value": 10,
        "value_type": "COUNT",
        "observed_at_utc": "2026-09-05T10:00:00Z"
      }
    ]"""
    imported = _import_plan(payload, AnalyticsPlatform.INSTAGRAM)
    analytics = build_analytics_brain(imported.analytics_request)
    result = build_metric_normalizer(MetricNormalizerRequest(analytics=analytics))

    item = result.observations[0]
    assert item.normalization_status == NormalizationStatus.NATIVE_ONLY
    assert item.canonical_metric is None
    assert item.cross_platform_equivalence_assumed is False
    assert result.cross_platform_equivalence_assumed is False


def test_real_f33_insufficient_cohort_never_creates_composite_score():
    payload = """[
      {
        "content_id": "video-1",
        "native_metric_name": "views",
        "value": 100,
        "value_type": "COUNT",
        "observed_at_utc": "2026-09-05T10:00:00Z"
      }
    ]"""
    imported = _import_plan(payload, AnalyticsPlatform.YOUTUBE)
    analytics = build_analytics_brain(imported.analytics_request)
    normalized = build_metric_normalizer(
        MetricNormalizerRequest(analytics=analytics)
    )
    result = build_performance_signals(
        PerformanceSignalsRequest(
            metrics=normalized,
            minimum_cohort_size=5,
        )
    )

    assert result.status == PerformanceSignalStatus.INSUFFICIENT_COHORT
    assert result.composite_score_enabled is False
    assert result.cross_platform_ranking is False
    assert result.causal_claims is False
    assert all(item.composite_score is None for item in result.signals)


def test_f33_minimum_cohort_is_pydantic_authoritative():
    payload = """[
      {
        "content_id": "video-1",
        "native_metric_name": "views",
        "value": 100,
        "value_type": "COUNT",
        "observed_at_utc": "2026-09-05T10:00:00Z"
      }
    ]"""
    imported = _import_plan(payload, AnalyticsPlatform.YOUTUBE)
    analytics = build_analytics_brain(imported.analytics_request)
    normalized = build_metric_normalizer(
        MetricNormalizerRequest(analytics=analytics)
    )

    with pytest.raises(ValueError):
        PerformanceSignalsRequest(
            metrics=normalized,
            minimum_cohort_size=2,
        )


def test_real_f34_is_descriptive_without_interpolation_or_recommendation():
    payload = """[
      {
        "content_id": "video-1",
        "native_metric_name": "audienceWatchRatio",
        "value": 0.90,
        "value_type": "RATIO",
        "observed_at_utc": "2026-09-05T10:00:00Z",
        "position_ratio": 0.10
      },
      {
        "content_id": "video-1",
        "native_metric_name": "audienceWatchRatio",
        "value": 0.55,
        "value_type": "RATIO",
        "observed_at_utc": "2026-09-05T10:00:01Z",
        "position_ratio": 0.50
      }
    ]"""
    imported = _import_plan(payload, AnalyticsPlatform.YOUTUBE)
    analytics = build_analytics_brain(imported.analytics_request)
    normalized = build_metric_normalizer(
        MetricNormalizerRequest(analytics=analytics)
    )
    result = build_retention_intelligence(
        RetentionIntelligenceRequest(metrics=normalized)
    )

    assert result.status == RetentionStatus.RETENTION_CURVES_READY
    assert result.curve_count == 1
    assert result.insights[0].point_count == 2
    assert result.interpolates_missing_points is False
    assert result.recommendations_generated is False
    assert result.causal_claims is False
    assert result.insights[0].recommendation is None
    assert result.insights[0].causal_claim is False
