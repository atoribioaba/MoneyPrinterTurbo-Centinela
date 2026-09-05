from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

from app.models.analytics_brain import AnalyticsPlatform
from app.models.evidence_recommendation_gate import (
    EvidenceRecommendationGateRequest,
    EvidenceRecommendationStatus,
)
from app.models.experiment_evidence_ledger import (
    ExperimentEvidenceLedgerRequest,
    ExperimentEvidenceStatus,
    ExperimentResultInput,
)
from app.models.experiment_planner import (
    ExperimentHypothesis,
    ExperimentPlannerPlan,
    ExperimentPlannerStatus,
)
from app.services.evidence_recommendation_gate import (
    build_evidence_recommendation_gate,
)
from app.services.experiment_evidence_ledger import (
    build_experiment_evidence_ledger,
)


ROOT = Path(__file__).resolve().parents[2]
PAGE_F39 = ROOT / "webui/pages/39_Experiment_Evidence_Ledger.py"
PAGE_F40 = ROOT / "webui/pages/40_Evidence_Recommendation_Gate.py"
NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(path: Path) -> ast.AST:
    return ast.parse(_source(path))


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


def _planner() -> ExperimentPlannerPlan:
    hypothesis = ExperimentHypothesis(
        hypothesis_id="hook-v1",
        variable="hook_duration_seconds",
        rationale="Controlled candidate for human execution.",
        evidence_refs=["retention:fixture"],
        control_definition="5 seconds",
        variant_definition="3 seconds",
        success_metric="AUDIENCE_WATCH_RATIO",
    )
    return ExperimentPlannerPlan(
        source_performance_hash="performance",
        source_retention_hash="retention",
        status=ExperimentPlannerStatus.CANDIDATE_EXPERIMENTS_READY,
        evidence_sufficient=True,
        hypothesis_count=1,
        hypotheses=[hypothesis],
        experiment_planner_hash="planner",
        generated_at_utc=NOW,
    )


def _result(**overrides) -> ExperimentResultInput:
    payload = {
        "experiment_id": "exp-1",
        "hypothesis_id": "hook-v1",
        "platform": AnalyticsPlatform.YOUTUBE,
        "success_metric": "AUDIENCE_WATCH_RATIO",
        "control_n": 10,
        "variant_n": 10,
        "control_metric_mean": 0.60,
        "variant_metric_mean": 0.66,
        "higher_is_better": True,
        "randomized_assignment_confirmed": True,
        "same_measurement_window_confirmed": True,
        "human_reviewed": True,
    }
    payload.update(overrides)
    return ExperimentResultInput(**payload)


def _ledger(*results: ExperimentResultInput):
    return build_experiment_evidence_ledger(
        ExperimentEvidenceLedgerRequest(
            planner=_planner(),
            results=list(results),
        )
    )


def test_f39_page_uses_real_models_request_and_service():
    tree = _tree(PAGE_F39)
    assert _imports_symbol(
        tree,
        "app.models.experiment_planner",
        "ExperimentPlannerPlan",
    )
    assert _imports_symbol(
        tree,
        "app.models.experiment_evidence_ledger",
        "ExperimentResultInput",
    )
    assert _imports_symbol(
        tree,
        "app.models.experiment_evidence_ledger",
        "ExperimentEvidenceLedgerRequest",
    )
    assert _imports_symbol(
        tree,
        "app.services.experiment_evidence_ledger",
        "build_experiment_evidence_ledger",
    )
    assert _calls_symbol(tree, "ExperimentResultInput")
    assert _calls_symbol(tree, "ExperimentEvidenceLedgerRequest")
    assert _calls_symbol(tree, "build_experiment_evidence_ledger")


def test_f40_page_uses_real_models_request_and_service():
    tree = _tree(PAGE_F40)
    assert _imports_symbol(
        tree,
        "app.models.experiment_evidence_ledger",
        "ExperimentEvidenceLedgerPlan",
    )
    assert _imports_symbol(
        tree,
        "app.models.evidence_recommendation_gate",
        "EvidenceRecommendationGateRequest",
    )
    assert _imports_symbol(
        tree,
        "app.services.evidence_recommendation_gate",
        "build_evidence_recommendation_gate",
    )
    assert _calls_symbol(tree, "EvidenceRecommendationGateRequest")
    assert _calls_symbol(tree, "build_evidence_recommendation_gate")


def test_f39_page_validates_f35_and_defaults_attestations_false():
    source = _source(PAGE_F39)
    assert "ExperimentPlannerPlan.model_validate_json" in source
    for name in (
        "randomized_assignment_confirmed",
        "same_measurement_window_confirmed",
        "human_reviewed",
    ):
        assert name in source
    assert source.count("value=False") >= 4
    assert "results = []" in source
    assert "No se ha fabricado evidencia" in source


def test_f39_service_waits_when_no_results_are_supplied():
    output = _ledger()
    assert output.status == ExperimentEvidenceStatus.WAITING_FOR_EXPERIMENT_RESULTS
    assert output.result_count == 0
    assert output.eligible_result_count == 0
    assert output.records == []


def test_f39_eligibility_requires_all_three_human_confirmations():
    eligible = _ledger(_result())
    assert eligible.eligible_result_count == 1
    assert eligible.records[0].eligible_for_recommendation_review is True

    unreviewed = _ledger(_result(human_reviewed=False))
    assert unreviewed.eligible_result_count == 0

    unrandomized = _ledger(
        _result(randomized_assignment_confirmed=False)
    )
    assert unrandomized.eligible_result_count == 0

    different_window = _ledger(
        _result(same_measurement_window_confirmed=False)
    )
    assert different_window.eligible_result_count == 0


def test_f39_guardrails_remain_planning_only_and_descriptive():
    output = _ledger(_result())
    assert output.planning_only is True
    assert output.runs_experiments is False
    assert output.calculates_p_values is False
    assert output.causal_claims is False
    assert output.database_writes == 0
    assert output.network_calls == 0
    assert output.auto_apply is False
    assert output.auto_publication is False


def test_f40_waits_without_eligible_improved_results():
    output = build_evidence_recommendation_gate(
        EvidenceRecommendationGateRequest(
            ledger=_ledger(_result(human_reviewed=False))
        )
    )
    assert (
        output.status
        == EvidenceRecommendationStatus.WAITING_FOR_CONFIRMED_EXPERIMENT_RESULTS
    )
    assert output.recommendation_count == 0


def test_f40_creates_candidate_only_from_eligible_improvement():
    output = build_evidence_recommendation_gate(
        EvidenceRecommendationGateRequest(ledger=_ledger(_result()))
    )
    assert (
        output.status
        == EvidenceRecommendationStatus.CANDIDATE_RECOMMENDATIONS_READY
    )
    assert output.recommendation_count == 1
    item = output.recommendations[0]
    assert item.requires_human_approval is True
    assert item.auto_apply is False
    assert item.auto_publish is False


def test_f40_rejects_non_improving_variant_as_recommendation():
    output = build_evidence_recommendation_gate(
        EvidenceRecommendationGateRequest(
            ledger=_ledger(_result(variant_metric_mean=0.55))
        )
    )
    assert output.recommendation_count == 0


def test_batch_p_pages_are_mobile_safe_and_fail_closed():
    for page in (PAGE_F39, PAGE_F40):
        source = _source(page)
        assert "st.columns(" not in source
        assert "st.dataframe(" not in source
        assert "st.table(" not in source
        assert "st.json(" not in source
        assert 'st.expander("Detalles técnicos", expanded=False)' in source
        assert 'st.code(f"{type(exc).__name__}: {exc}", language=None)' in source
        assert "except Exception as exc:" in source


def test_batch_p_pages_do_not_call_policy_or_side_effect_paths():
    combined = (_source(PAGE_F39) + "\n" + _source(PAGE_F40)).lower()
    forbidden = (
        "from app.services.policy_candidate",
        "build_policy_candidate(",
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
        assert token not in combined


def test_f40_plan_guardrails_remain_false():
    output = build_evidence_recommendation_gate(
        EvidenceRecommendationGateRequest(ledger=_ledger(_result()))
    )
    assert output.planning_only is True
    assert output.association_only_recommendations is False
    assert output.causal_claims is False
    assert output.edits_project is False
    assert output.updates_director_policy is False
    assert output.auto_apply is False
    assert output.auto_publication is False
    assert output.uses_llm is False
    assert output.network_calls == 0
