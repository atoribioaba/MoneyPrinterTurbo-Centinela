from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.analytics_brain import AnalyticsPlatform, NativeMetricObservation
from app.models.astronomy_director import AstronomyVideoPlan, ScenePlan
from app.models.association_analyzer import (
    AssociationAnalyzerRequest,
    AssociationAnalyzerStatus,
)
from app.models.content_feature_registry import (
    ContentBinding,
    ContentBindingStatus,
    ContentFeatureRegistryRequest,
)
from app.models.metric_normalizer import (
    CanonicalMetric,
    MetricNormalizerPlan,
    NormalizationStatus,
    NormalizedMetricObservation,
)
from app.models.outcome_linker import OutcomeLinkerPlan, OutcomeLinkerRequest
from app.models.outcome_linker import OutcomeLinkerStatus
from app.models.visual_story_graph import VisualStoryGraph, VisualStoryNode
from app.services.association_analyzer import build_association_analyzer
from app.services.content_feature_registry import build_content_feature_registry
from app.services.outcome_linker import build_outcome_linker


ROOT = Path(__file__).resolve().parents[2]
PAGES = {
    "F36": ROOT / "webui/pages/36_Content_Feature_Registry.py",
    "F37": ROOT / "webui/pages/37_Outcome_Linker.py",
    "F38": ROOT / "webui/pages/38_Association_Analyzer.py",
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


def _f36_request(binding: ContentBinding | None = None):
    scenes = [
        ScenePlan.model_construct(
            scene_number=1,
            duration_seconds=10,
            narration="uno",
            claims=[],
            ai_recreation_allowed=False,
            astronomy_objects=["Luna"],
        ),
        ScenePlan.model_construct(
            scene_number=2,
            duration_seconds=20,
            narration="dos",
            claims=[],
            ai_recreation_allowed=False,
            astronomy_objects=["Sol"],
        ),
    ]
    plan = AstronomyVideoPlan.model_construct(
        subject="Fixture",
        hook="Hook de prueba",
        context_hash="ctx",
        total_duration_seconds=30,
        scenes=scenes,
    )
    graph = VisualStoryGraph.model_construct(
        source_plan_context_hash="ctx",
        graph_hash="graph",
        node_count=2,
        placeholder_count=0,
        climax_node_id="n2",
        nodes=[
            VisualStoryNode.model_construct(
                node_id="n1",
                scene_number=1,
                intensity=0.2,
                placeholder=False,
            ),
            VisualStoryNode.model_construct(
                node_id="n2",
                scene_number=2,
                intensity=0.9,
                placeholder=False,
            ),
        ],
    )
    return ContentFeatureRegistryRequest.model_construct(
        plan=plan,
        story_graph=graph,
        binding=binding,
    )


def _metric_plan(
    content_id: str,
    *,
    status: NormalizationStatus = NormalizationStatus.NORMALIZED_VERIFIED,
):
    source = NativeMetricObservation.model_construct(
        platform=AnalyticsPlatform.YOUTUBE,
        content_id=content_id,
        native_metric_name="views",
        value=100.0,
        observed_at_utc=datetime(2026, 9, 5, tzinfo=timezone.utc),
    )
    item = NormalizedMetricObservation.model_construct(
        source=source,
        canonical_metric=(
            CanonicalMetric.VIEW_COUNT
            if status == NormalizationStatus.NORMALIZED_VERIFIED
            else None
        ),
        normalization_status=status,
    )
    return MetricNormalizerPlan.model_construct(
        observations=[item],
        metric_normalizer_hash="metrics",
    )


def test_f36_page_uses_real_models_service_and_optional_binding():
    tree = _tree("F36")
    assert _imports_symbol(
        tree,
        "app.models.content_feature_registry",
        "ContentFeatureRegistryRequest",
    )
    assert _imports_symbol(
        tree,
        "app.services.content_feature_registry",
        "build_content_feature_registry",
    )
    assert _calls_symbol(tree, "ContentFeatureRegistryRequest")
    assert _calls_symbol(tree, "build_content_feature_registry")
    source = _source("F36")
    assert "AstronomyVideoPlan.model_validate_json" in source
    assert "VisualStoryGraph.model_validate_json" in source
    assert "ContentBinding(" in source


def test_f37_page_uses_real_models_and_service_without_join_reimplementation():
    tree = _tree("F37")
    assert _imports_symbol(
        tree,
        "app.models.outcome_linker",
        "OutcomeLinkerRequest",
    )
    assert _imports_symbol(
        tree,
        "app.services.outcome_linker",
        "build_outcome_linker",
    )
    assert _calls_symbol(tree, "OutcomeLinkerRequest")
    assert _calls_symbol(tree, "build_outcome_linker")
    source = _source("F37")
    assert "NORMALIZED_VERIFIED" not in source
    assert "snapshot_by_key" not in source
    assert "cross_platform_join =" not in source


def test_f38_page_uses_real_pydantic_request_and_real_service():
    tree = _tree("F38")
    assert _imports_symbol(
        tree,
        "app.models.association_analyzer",
        "AssociationAnalyzerRequest",
    )
    assert _imports_symbol(
        tree,
        "app.services.association_analyzer",
        "build_association_analyzer",
    )
    assert _calls_symbol(tree, "AssociationAnalyzerRequest")
    assert _calls_symbol(tree, "build_association_analyzer")
    source = _source("F38")
    assert "minimum_sample_size_text" in source
    assert "min_value=" not in source
    assert "max_value=" not in source


def test_batch_n_pages_are_mobile_product_safe_and_fail_closed():
    for module in PAGES:
        source = _source(module)
        assert "st.columns(" not in source
        assert "st.dataframe(" not in source
        assert "st.table(" not in source
        assert "st.json(" not in source
        assert 'st.expander("Detalles técnicos", expanded=False)' in source
        assert 'st.code(f"{type(exc).__name__}: {exc}", language=None)' in source
        assert "except Exception as exc:" in source


def test_batch_n_pages_do_not_call_f35_f39_policy_or_side_effect_paths():
    joined = "\n".join(_source(module) for module in PAGES)
    forbidden = (
        "build_experiment_planner(",
        "build_experiment_evidence_ledger(",
        "build_evidence_recommendation_gate(",
        "build_policy_candidate(",
        "build_policy_simulator(",
        "build_policy_comparator(",
        "mark_published",
        "authorization_to_publish",
        "sqlite3",
        "requests.",
        "httpx.",
        "subprocess.",
    )
    for marker in forbidden:
        assert marker not in joined, marker


def test_real_f36_unbound_waits_and_bound_keeps_explicit_identity():
    unbound = build_content_feature_registry(_f36_request())
    assert unbound.status == ContentBindingStatus.WAITING_FOR_CONTENT_BINDING
    assert unbound.bound_snapshot_count == 0
    assert unbound.stores_creative_text is False
    assert unbound.analyzes_pixels is False
    assert unbound.network_calls == 0
    assert unbound.database_writes == 0

    binding = ContentBinding(
        platform=AnalyticsPlatform.YOUTUBE,
        content_id="video-1",
    )
    bound = build_content_feature_registry(_f36_request(binding))
    snapshot = bound.snapshots[0]
    assert bound.status == ContentBindingStatus.BOUND_TO_CONTENT
    assert snapshot.platform == AnalyticsPlatform.YOUTUBE
    assert snapshot.content_id == "video-1"


def test_real_f37_requires_bound_content_and_verified_normalized_metric():
    unbound_features = build_content_feature_registry(_f36_request())
    waiting = build_outcome_linker(
        OutcomeLinkerRequest.model_construct(
            features=unbound_features,
            metrics=_metric_plan("video-1"),
        )
    )
    assert waiting.status == OutcomeLinkerStatus.WAITING_FOR_BOUND_CONTENT_ANALYTICS
    assert waiting.record_count == 0

    binding = ContentBinding(
        platform=AnalyticsPlatform.YOUTUBE,
        content_id="video-1",
    )
    bound_features = build_content_feature_registry(_f36_request(binding))
    native_only = build_outcome_linker(
        OutcomeLinkerRequest.model_construct(
            features=bound_features,
            metrics=_metric_plan(
                "video-1",
                status=NormalizationStatus.NATIVE_ONLY,
            ),
        )
    )
    assert native_only.record_count == 0
    assert native_only.joins_native_only_metrics is False
    assert native_only.cross_platform_join is False
    assert native_only.interpolates_observations is False

    joined = build_outcome_linker(
        OutcomeLinkerRequest.model_construct(
            features=bound_features,
            metrics=_metric_plan("video-1"),
        )
    )
    assert joined.status == OutcomeLinkerStatus.JOINED_OUTCOMES_READY
    assert joined.record_count == 1
    assert joined.records[0].content_id == "video-1"


def test_f38_minimum_sample_size_is_pydantic_authoritative():
    joined = OutcomeLinkerPlan.model_construct(
        outcome_linker_hash="joined",
        records=[],
    )
    with pytest.raises(ValueError):
        AssociationAnalyzerRequest(joined=joined, minimum_sample_size=4)

    with pytest.raises(ValueError):
        AssociationAnalyzerRequest(joined=joined, minimum_sample_size=1001)


def test_real_f38_preserves_descriptive_only_insufficient_semantics():
    binding = ContentBinding(
        platform=AnalyticsPlatform.YOUTUBE,
        content_id="video-1",
    )
    features = build_content_feature_registry(_f36_request(binding))
    joined = build_outcome_linker(
        OutcomeLinkerRequest.model_construct(
            features=features,
            metrics=_metric_plan("video-1"),
        )
    )
    result = build_association_analyzer(
        AssociationAnalyzerRequest(
            joined=joined,
            minimum_sample_size=5,
        )
    )

    assert result.status == AssociationAnalyzerStatus.INSUFFICIENT_SAMPLE
    assert result.method == "SPEARMAN_RANK_CORRELATION"
    assert result.cross_platform_pooling is False
    assert result.p_values_calculated is False
    assert result.statistical_significance_claimed is False
    assert result.causal_claims is False
    assert result.network_calls == 0
    assert result.auto_publication is False
