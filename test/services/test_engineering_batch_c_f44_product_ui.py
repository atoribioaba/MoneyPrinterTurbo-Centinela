from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.human_policy_approval import (
    HumanDecision,
    HumanPolicyApprovalRequest,
    PolicyHumanDecision,
)
from app.models.policy_comparator import (
    PolicyComparatorPlan,
    PolicyComparatorStatus,
    PolicyComparison,
)
from app.services.human_policy_approval import (
    HumanPolicyApprovalError,
    build_human_policy_approval,
)


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "webui/pages/44_Human_Policy_Approval.py"
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


def _comparison(candidate_id: str, safe: bool = True) -> PolicyComparison:
    return PolicyComparison(
        policy_candidate_id=candidate_id,
        simulation_count=1,
        behavior_change_count=1,
        structural_regression_count=0 if safe else 1,
        placeholder_regression_count=0,
        safe_for_human_review=safe,
    )


def _comparator(*comparisons: PolicyComparison) -> PolicyComparatorPlan:
    safe_count = sum(item.safe_for_human_review for item in comparisons)
    if not comparisons:
        status = PolicyComparatorStatus.WAITING_FOR_SIMULATIONS
    elif safe_count:
        status = PolicyComparatorStatus.SAFE_CANDIDATES_READY
    else:
        status = PolicyComparatorStatus.NO_SAFE_CANDIDATES
    return PolicyComparatorPlan(
        source_policy_simulator_hash="sim-hash",
        status=status,
        candidate_count=len(comparisons),
        safe_candidate_count=safe_count,
        comparisons=list(comparisons),
        policy_comparator_hash="cmp-hash",
        generated_at_utc=NOW,
    )


def _decision(candidate_id: str, kind: HumanDecision) -> PolicyHumanDecision:
    return PolicyHumanDecision(
        policy_candidate_id=candidate_id,
        decision=kind,
        reviewer_ref="reviewer-1",
        rationale="Revisión humana explícita de la simulación y del comparator.",
        decided_at_utc=NOW,
    )


def test_f44_page_imports_and_calls_real_contract():
    tree = _tree()
    for symbol in (
        "HumanPolicyApprovalRequest",
        "PolicyHumanDecision",
    ):
        assert _imports_symbol(tree, "app.models.human_policy_approval", symbol)
    assert _imports_symbol(
        tree, "app.services.human_policy_approval", "HumanPolicyApprovalError"
    )
    assert _imports_symbol(
        tree, "app.services.human_policy_approval", "build_human_policy_approval"
    )
    assert _calls_symbol(tree, "PolicyHumanDecision")
    assert _calls_symbol(tree, "HumanPolicyApprovalRequest")
    assert _calls_symbol(tree, "build_human_policy_approval")


def test_f44_page_loads_real_f41_f42_f43_context_in_memory():
    source = _source()
    assert "PolicyCandidatePlan" in source
    assert "PolicySimulatorPlan" in source
    assert "PolicyComparatorPlan" in source
    assert source.count("st.file_uploader(") == 3
    assert "model_validate_json" in source
    assert "policy_candidate_id" in source
    assert "baseline_value" in source
    assert "candidate_value" in source
    assert "evidence_class" in source
    assert "behavior_changed" in source
    assert "structural_regression_count" in source
    assert "placeholder_regression_count" in source


def test_f44_page_validates_lineage_and_never_repairs_hashes():
    source = _source()
    assert "f42.source_policy_candidate_hash == f41.policy_candidate_hash" in source
    assert "f43.source_policy_simulator_hash == f42.policy_simulator_hash" in source
    assert "La trazabilidad de este candidato no coincide" in source
    forbidden = (
        "policy_candidate_hash =",
        "policy_simulator_hash =",
        "source_policy_candidate_hash =",
        "source_policy_simulator_hash =",
    )
    for marker in forbidden:
        assert marker not in source, marker


def test_f44_page_consumes_f43_safe_gate_without_reimplementing_comparator():
    source = _source()
    assert "selected_comparison.safe_for_human_review" in source
    assert "No existe bypass desde F44" in source
    assert "structural_regression_count == 0" not in source
    assert "placeholder_regression_count == 0" not in source
    assert "build_policy_comparator(" not in source
    assert "build_policy_simulator(" not in source


def test_f44_page_has_no_default_or_automatic_approval():
    source = _source()
    assert 'st.button(\n                "Aprobar"' in source
    assert 'st.button(\n                "Rechazar"' in source
    assert "st.radio(" not in source
    assert "st.toggle(" not in source
    assert "st.checkbox(" not in source
    assert 'value="APPROVE"' not in source
    assert "decision_enabled = (" in source
    assert "disabled=not decision_enabled" in source
    assert "if reject_clicked or approve_clicked:" in source


def test_f44_page_requires_reviewer_rationale_and_decision_time_is_utc():
    source = _source()
    assert 'st.text_input(\n                "Reviewer ref"' in source
    assert 'st.text_area(\n                "Rationale"' in source
    assert "reviewer_ref.strip() and rationale.strip()" in source
    assert "datetime.now(timezone.utc)" in source
    assert "decided_at_utc=datetime.now(timezone.utc)" in source


def test_f44_page_is_mobile_safe_and_keeps_raw_errors_secondary():
    source = _source()
    assert "st.columns(" not in source
    assert "st.dataframe(" not in source
    assert "st.table(" not in source
    assert 'st.expander("Detalles técnicos", expanded=False)' in source
    assert 'st.code(f"{type(exc).__name__}: {exc}", language=None)' in source
    assert "No se ha podido completar la revisión humana de forma segura" in source


def test_f44_page_introduces_no_registry_activation_network_or_publication_route():
    source = _source()
    forbidden = (
        "build_policy_registry(",
        "activate_policy(",
        "promote_policy(",
        "write_runtime_config(",
        "requests.",
        "httpx.",
        "urllib.",
        "webhook",
        "mark_published",
        "authorization_to_publish",
        "ArtifactStore",
        "sqlite3",
    )
    for marker in forbidden:
        assert marker not in source, marker


def test_f44_real_service_records_one_explicit_approve_without_activation():
    comparator = _comparator(_comparison("p1"), _comparison("p2"))
    result = build_human_policy_approval(
        HumanPolicyApprovalRequest(
            comparator=comparator,
            decisions=[_decision("p1", HumanDecision.APPROVE)],
        )
    )
    assert result.decision_count == 1
    assert result.approved_count == 1
    assert result.rejected_count == 0
    assert result.pending_count == 1
    assert not result.auto_approval
    assert not result.activates_policy
    assert not result.edits_project
    assert result.network_calls == 0
    assert not result.auto_publication


def test_f44_real_service_records_reject_as_valid_human_decision():
    result = build_human_policy_approval(
        HumanPolicyApprovalRequest(
            comparator=_comparator(_comparison("p1")),
            decisions=[_decision("p1", HumanDecision.REJECT)],
        )
    )
    assert result.decision_count == 1
    assert result.rejected_count == 1
    assert result.approved_count == 0
    assert result.records[0].decision == HumanDecision.REJECT


def test_f44_real_service_rejects_unsafe_candidate_fail_closed():
    with pytest.raises(HumanPolicyApprovalError, match="not safe for review"):
        build_human_policy_approval(
            HumanPolicyApprovalRequest(
                comparator=_comparator(_comparison("p1", safe=False)),
                decisions=[_decision("p1", HumanDecision.APPROVE)],
            )
        )


def test_f44_decision_timestamp_is_timezone_aware_utc():
    decision = PolicyHumanDecision(
        policy_candidate_id="p1",
        decision=HumanDecision.APPROVE,
        reviewer_ref="reviewer-1",
        rationale="Decisión explícita.",
        decided_at_utc=datetime.now(timezone.utc),
    )
    assert decision.decided_at_utc.tzinfo is not None
    assert decision.decided_at_utc.utcoffset().total_seconds() == 0
