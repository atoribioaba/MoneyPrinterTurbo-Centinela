from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.analytics_brain import AnalyticsPlatform
from app.models.evidence_recommendation_gate import (
    CandidateRecommendation,
    EvidenceRecommendationGatePlan,
    EvidenceRecommendationStatus,
)
from app.models.policy_candidate import (
    PolicyBinding,
    PolicyCandidateRequest,
    PolicyCandidateStatus,
)
from app.models.policy_comparator import (
    PolicyComparatorRequest,
    PolicyComparatorStatus,
)
from app.models.policy_simulator import (
    PolicySimulationResult,
    PolicySimulatorPlan,
    PolicySimulatorRequest,
    PolicySimulatorStatus,
)
from app.services.policy_candidate import build_policy_candidate
from app.services.policy_comparator import build_policy_comparator
from app.services.policy_simulator import build_policy_simulator


ROOT = Path(__file__).resolve().parents[2]
PAGE_F41 = ROOT / "webui/pages/41_Policy_Candidate.py"
PAGE_F42 = ROOT / "webui/pages/42_Policy_Simulator.py"
PAGE_F43 = ROOT / "webui/pages/43_Policy_Comparator.py"
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


def _recommendations() -> EvidenceRecommendationGatePlan:
    recommendation = CandidateRecommendation(
        recommendation_id="rec-1",
        experiment_id="exp-1",
        hypothesis_id="hyp-1",
        platform=AnalyticsPlatform.YOUTUBE,
        variable="cinematic_intensity_bias",
        recommended_definition="0.05",
        success_metric="AUDIENCE_WATCH_RATIO",
        observed_delta=0.05,
    )
    return EvidenceRecommendationGatePlan(
        source_experiment_evidence_ledger_hash="ledger",
        status=EvidenceRecommendationStatus.CANDIDATE_RECOMMENDATIONS_READY,
        recommendation_count=1,
        recommendations=[recommendation],
        evidence_recommendation_gate_hash="gate",
        generated_at_utc=NOW,
    )


def _candidate_plan():
    return build_policy_candidate(
        PolicyCandidateRequest(
            recommendations=_recommendations(),
            bindings=[
                PolicyBinding(
                    recommendation_id="rec-1",
                    parameter="intensity_bias",
                    baseline_value=0.0,
                    candidate_value=0.05,
                    human_mapping_confirmed=True,
                )
            ],
        )
    )


def _simulation_plan(
    *,
    behavior_changed: bool = False,
    structural_ok: bool = True,
    placeholders_preserved: bool = True,
) -> PolicySimulatorPlan:
    row = PolicySimulationResult(
        policy_candidate_id="candidate-1",
        case_id="case-1",
        parameter="intensity_bias",
        baseline_direction_hash="base",
        candidate_direction_hash="candidate",
        behavior_changed=behavior_changed,
        baseline_tension_curve=[0.2, 0.9],
        candidate_tension_curve=[0.2, 0.9],
        baseline_climax_scene=2,
        candidate_climax_scene=2,
        baseline_structural_checks_pass=True,
        candidate_structural_checks_pass=structural_ok,
        placeholders_preserved=placeholders_preserved,
    )
    return PolicySimulatorPlan(
        source_policy_candidate_hash="candidate-plan",
        status=PolicySimulatorStatus.SIMULATIONS_READY,
        case_count=1,
        simulation_count=1,
        behavior_change_count=int(behavior_changed),
        results=[row],
        policy_simulator_hash="simulator",
        generated_at_utc=NOW,
    )


def test_f41_page_uses_real_contract_and_service():
    tree = _tree(PAGE_F41)
    assert _imports_symbol(
        tree,
        "app.models.evidence_recommendation_gate",
        "EvidenceRecommendationGatePlan",
    )
    assert _imports_symbol(
        tree,
        "app.models.policy_candidate",
        "PolicyBinding",
    )
    assert _imports_symbol(
        tree,
        "app.models.policy_candidate",
        "PolicyCandidateRequest",
    )
    assert _imports_symbol(
        tree,
        "app.services.policy_candidate",
        "build_policy_candidate",
    )
    assert _calls_symbol(tree, "PolicyBinding")
    assert _calls_symbol(tree, "PolicyCandidateRequest")
    assert _calls_symbol(tree, "build_policy_candidate")


def test_f42_page_uses_real_contract_and_service():
    tree = _tree(PAGE_F42)
    assert _imports_symbol(
        tree,
        "app.models.policy_candidate",
        "PolicyCandidatePlan",
    )
    assert _imports_symbol(
        tree,
        "app.models.policy_simulator",
        "PolicySimulationCase",
    )
    assert _imports_symbol(
        tree,
        "app.models.policy_simulator",
        "PolicySimulatorRequest",
    )
    assert _imports_symbol(
        tree,
        "app.services.policy_simulator",
        "build_policy_simulator",
    )
    assert _calls_symbol(tree, "PolicySimulatorRequest")
    assert _calls_symbol(tree, "build_policy_simulator")


def test_f43_page_uses_real_contract_and_service():
    tree = _tree(PAGE_F43)
    assert _imports_symbol(
        tree,
        "app.models.policy_simulator",
        "PolicySimulatorPlan",
    )
    assert _imports_symbol(
        tree,
        "app.models.policy_comparator",
        "PolicyComparatorRequest",
    )
    assert _imports_symbol(
        tree,
        "app.services.policy_comparator",
        "build_policy_comparator",
    )
    assert _calls_symbol(tree, "PolicyComparatorRequest")
    assert _calls_symbol(tree, "build_policy_comparator")


def test_f41_requires_explicit_confirmed_binding():
    waiting = build_policy_candidate(
        PolicyCandidateRequest(recommendations=_recommendations())
    )
    assert waiting.status == PolicyCandidateStatus.WAITING_FOR_EXPLICIT_POLICY_BINDINGS

    unconfirmed = build_policy_candidate(
        PolicyCandidateRequest(
            recommendations=_recommendations(),
            bindings=[
                PolicyBinding(
                    recommendation_id="rec-1",
                    parameter="intensity_bias",
                    baseline_value=0.0,
                    candidate_value=0.05,
                    human_mapping_confirmed=False,
                )
            ],
        )
    )
    assert unconfirmed.candidate_count == 0

    ready = _candidate_plan()
    assert ready.status == PolicyCandidateStatus.CANDIDATE_POLICIES_READY
    assert ready.candidates[0].requires_simulation is True
    assert ready.candidates[0].approved_for_activation is False
    assert ready.inferred_bindings is False
    assert ready.activates_policy is False


def test_f41_rejects_unsupported_range_and_equal_values():
    bad_payloads = [
        dict(parameter="invented", baseline_value=0.0, candidate_value=0.05),
        dict(
            parameter="intensity_bias",
            baseline_value=0.0,
            candidate_value=0.5,
        ),
        dict(
            parameter="intensity_bias",
            baseline_value=0.05,
            candidate_value=0.05,
        ),
    ]
    for payload in bad_payloads:
        with pytest.raises(RuntimeError):
            build_policy_candidate(
                PolicyCandidateRequest(
                    recommendations=_recommendations(),
                    bindings=[
                        PolicyBinding(
                            recommendation_id="rec-1",
                            human_mapping_confirmed=True,
                            **payload,
                        )
                    ],
                )
            )


def test_f42_waits_without_cases_and_never_renders():
    output = build_policy_simulator(
        PolicySimulatorRequest(candidates=_candidate_plan())
    )
    assert output.status == PolicySimulatorStatus.WAITING_FOR_CANDIDATE_POLICY_AND_CASES
    assert output.simulation_count == 0
    assert output.uses_real_cinematic_director is True
    assert output.renders_video is False
    assert output.gpu_required is False
    assert output.writes_runtime_config is False
    assert output.activates_policy is False
    assert output.network_calls == 0


def test_f43_safe_for_review_is_not_quality_or_causality():
    output = build_policy_comparator(
        PolicyComparatorRequest(simulations=_simulation_plan())
    )
    assert output.status == PolicyComparatorStatus.SAFE_CANDIDATES_READY
    assert output.safe_candidate_count == 1
    comparison = output.comparisons[0]
    assert comparison.behavior_change_count == 0
    assert comparison.safe_for_human_review is True
    assert comparison.quality_improvement_claimed is False
    assert comparison.causal_claim is False
    assert output.quality_improvement_claims is False
    assert output.causal_claims is False
    assert output.activates_policy is False


def test_f43_structural_or_placeholder_regression_is_unsafe():
    structural = build_policy_comparator(
        PolicyComparatorRequest(
            simulations=_simulation_plan(structural_ok=False)
        )
    )
    assert structural.status == PolicyComparatorStatus.NO_SAFE_CANDIDATES

    placeholder = build_policy_comparator(
        PolicyComparatorRequest(
            simulations=_simulation_plan(placeholders_preserved=False)
        )
    )
    assert placeholder.status == PolicyComparatorStatus.NO_SAFE_CANDIDATES


def test_f43_waits_without_simulations():
    empty = PolicySimulatorPlan(
        source_policy_candidate_hash="candidate-plan",
        status=PolicySimulatorStatus.WAITING_FOR_CANDIDATE_POLICY_AND_CASES,
        case_count=0,
        simulation_count=0,
        behavior_change_count=0,
        results=[],
        policy_simulator_hash="empty",
        generated_at_utc=NOW,
    )
    output = build_policy_comparator(
        PolicyComparatorRequest(simulations=empty)
    )
    assert output.status == PolicyComparatorStatus.WAITING_FOR_SIMULATIONS
    assert output.candidate_count == 0
    assert output.safe_candidate_count == 0


def test_batch_q_pages_are_mobile_safe_and_fail_closed():
    for page in (PAGE_F41, PAGE_F42, PAGE_F43):
        source = _source(page)
        assert "st.columns(" not in source
        assert "st.dataframe(" not in source
        assert "st.table(" not in source
        assert "st.json(" not in source
        assert 'st.expander("Detalles técnicos", expanded=False)' in source
        assert 'st.code(f"{type(exc).__name__}: {exc}", language=None)' in source
        assert "except Exception as exc:" in source


def test_batch_q_pages_do_not_auto_forward_or_mutate_policy():
    combined = (
        _source(PAGE_F41)
        + "\n"
        + _source(PAGE_F42)
        + "\n"
        + _source(PAGE_F43)
    ).lower()
    forbidden = (
        "from app.services.human_policy_approval",
        "build_human_policy_approval(",
        "policyhumandecision(",
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

    assert "approved_for_activation" in _source(PAGE_F41)
    assert "renders video" in _source(PAGE_F42).lower()
    assert "safe_for_human_review" in _source(PAGE_F43)
    assert "mejora demostrada" in _source(PAGE_F43)
