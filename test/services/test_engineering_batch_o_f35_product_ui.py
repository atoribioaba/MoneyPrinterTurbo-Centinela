from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.analytics_brain import AnalyticsPlatform
from app.models.experiment_planner import (
    ExperimentHypothesis,
    ExperimentPlannerRequest,
    ExperimentPlannerStatus,
)
from app.models.performance_signals import (
    ContentPerformanceSignal,
    PerformanceSignalsPlan,
    PerformanceSignalStatus,
)
from app.models.retention_intelligence import (
    RetentionInsight,
    RetentionIntelligencePlan,
    RetentionStatus,
)
from app.services.experiment_planner import build_experiment_planner


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "webui/pages/35_Experiment_Planner.py"
NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)


def _source() -> str:
    return PAGE.read_text(encoding="utf-8")


def _tree() -> ast.AST:
    return ast.parse(_source())


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


def _performance(status: PerformanceSignalStatus) -> PerformanceSignalsPlan:
    signals = []
    if status == PerformanceSignalStatus.COHORT_SIGNALS_READY:
        signals = [
            ContentPerformanceSignal(
                platform=AnalyticsPlatform.YOUTUBE,
                content_id="fixture-video",
                cohort_size=5,
                view_count=100.0,
                view_percentile_within_cohort=0.8,
            )
        ]
    return PerformanceSignalsPlan(
        source_metric_normalizer_hash="norm",
        status=status,
        content_count=len(signals),
        ready_signal_count=sum(
            item.view_percentile_within_cohort is not None
            or item.interaction_rate_percentile_within_cohort is not None
            for item in signals
        ),
        signals=signals,
        performance_signals_hash="performance",
        generated_at_utc=NOW,
    )


def _retention(status: RetentionStatus) -> RetentionIntelligencePlan:
    insights = []
    if status == RetentionStatus.RETENTION_CURVES_READY:
        insights = [
            RetentionInsight(
                platform=AnalyticsPlatform.YOUTUBE,
                content_id="fixture-video",
                point_count=2,
                first_10_percent_mean=1.0,
                midpoint_ratio=0.7,
                final_ratio=0.5,
                largest_drop_position_ratio=0.5,
                largest_drop_magnitude=0.3,
            )
        ]
    return RetentionIntelligencePlan(
        source_metric_normalizer_hash="norm",
        status=status,
        curve_count=len(insights),
        insights=insights,
        retention_intelligence_hash="retention",
        generated_at_utc=NOW,
    )


def _hypothesis(**overrides) -> ExperimentHypothesis:
    payload = {
        "hypothesis_id": "hook-v1",
        "variable": "hook_duration_seconds",
        "rationale": "Evidence-linked candidate, not a causal claim.",
        "evidence_refs": ["retention:video:largest_drop"],
        "control_definition": "Current approved hook duration.",
        "variant_definition": "One alternate approved hook duration.",
        "success_metric": "retention_first_10_percent",
    }
    payload.update(overrides)
    return ExperimentHypothesis(**payload)


def test_f35_page_uses_real_models_request_and_service():
    tree = _tree()
    assert _imports_symbol(
        tree,
        "app.models.performance_signals",
        "PerformanceSignalsPlan",
    )
    assert _imports_symbol(
        tree,
        "app.models.retention_intelligence",
        "RetentionIntelligencePlan",
    )
    assert _imports_symbol(
        tree,
        "app.models.experiment_planner",
        "ExperimentHypothesis",
    )
    assert _imports_symbol(
        tree,
        "app.models.experiment_planner",
        "ExperimentPlannerRequest",
    )
    assert _imports_symbol(
        tree,
        "app.services.experiment_planner",
        "build_experiment_planner",
    )
    assert _calls_symbol(tree, "ExperimentHypothesis")
    assert _calls_symbol(tree, "ExperimentPlannerRequest")
    assert _calls_symbol(tree, "build_experiment_planner")


def test_f35_page_validates_f33_f34_with_real_pydantic_models():
    source = _source()
    assert "PerformanceSignalsPlan.model_validate_json" in source
    assert "RetentionIntelligencePlan.model_validate_json" in source
    assert "json.loads(" not in source


def test_f35_page_has_explicit_human_hypothesis_fields():
    source = _source()
    for field in (
        "hypothesis_id",
        "variable",
        "rationale",
        "evidence_refs",
        "control_definition",
        "variant_definition",
        "success_metric",
    ):
        assert f'"{field}"' in source
    assert "ExperimentHypothesis(" in source
    assert "changes_one_variable_only=True" in source
    assert "auto_apply=False" in source
    assert "auto_publish=False" in source


def test_f35_page_does_not_reimplement_evidence_gate():
    source = _source()
    assert "PerformanceSignalStatus.COHORT_SIGNALS_READY" not in source
    assert "RetentionStatus.RETENTION_CURVES_READY" not in source
    assert "evidence_sufficient =" not in source
    assert "view_percentile" not in source
    assert "retention_first_10_percent >" not in source


def test_f35_service_waits_and_suppresses_hypothesis_without_evidence():
    result = build_experiment_planner(
        ExperimentPlannerRequest(
            performance=_performance(PerformanceSignalStatus.INSUFFICIENT_COHORT),
            retention=_retention(RetentionStatus.WAITING_FOR_RETENTION_DATA),
            candidate_hypotheses=[_hypothesis()],
        )
    )
    assert result.status == ExperimentPlannerStatus.WAITING_FOR_EVIDENCE
    assert result.evidence_sufficient is False
    assert result.hypothesis_count == 0
    assert result.hypotheses == []


def test_f35_service_releases_candidate_when_evidence_is_sufficient():
    result = build_experiment_planner(
        ExperimentPlannerRequest(
            performance=_performance(PerformanceSignalStatus.COHORT_SIGNALS_READY),
            retention=_retention(RetentionStatus.WAITING_FOR_RETENTION_DATA),
            candidate_hypotheses=[_hypothesis()],
        )
    )
    assert result.status == ExperimentPlannerStatus.CANDIDATE_EXPERIMENTS_READY
    assert result.evidence_sufficient is True
    assert result.hypothesis_count == 1
    assert result.hypotheses[0].hypothesis_id == "hook-v1"


def test_f35_one_variable_contract_fails_closed():
    with pytest.raises(ValueError):
        _hypothesis(changes_one_variable_only=False)


def test_f35_page_preserves_truthful_planning_only_copy():
    source = _source()
    assert "No se ejecuta ningún experimento" in source
    assert "revisión y ejecución humana" in source
    assert "no significa que el experimento esté aprobado" in source
    assert "ExperimentPlannerPlan" in source


def test_f35_page_does_not_call_downstream_or_side_effect_paths():
    source = _source()
    forbidden = (
        "experiment_evidence_ledger",
        "evidence_recommendation_gate",
        "policy_candidate",
        "requests.",
        "httpx",
        "urllib",
        "subprocess",
        "sqlite",
        "sqlalchemy",
        "torch",
        "cuda",
        "ollama",
        "publish(",
        "upload(",
        "webhook",
    )
    for token in forbidden:
        assert token not in source.lower()


def test_f35_page_is_mobile_safe_and_fail_closed():
    source = _source()
    assert "st.columns(" not in source
    assert "st.dataframe(" not in source
    assert "st.table(" not in source
    assert "st.json(" not in source
    assert 'st.expander("Detalles técnicos", expanded=False)' in source
    assert 'st.code(f"{type(exc).__name__}: {exc}", language=None)' in source
    assert "except Exception as exc:" in source


def test_f35_service_plan_guardrails_remain_false():
    result = build_experiment_planner(
        ExperimentPlannerRequest(
            performance=_performance(PerformanceSignalStatus.COHORT_SIGNALS_READY),
            retention=_retention(RetentionStatus.WAITING_FOR_RETENTION_DATA),
            candidate_hypotheses=[_hypothesis()],
        )
    )
    assert result.planning_only is True
    assert result.runs_experiments is False
    assert result.edits_project is False
    assert result.publishes_content is False
    assert result.causal_claims is False
    assert result.uses_llm is False
    assert result.network_calls == 0
