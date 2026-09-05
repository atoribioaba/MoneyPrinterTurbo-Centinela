from __future__ import annotations

import ast
from pathlib import Path


PAGE = Path("webui/pages/51_Production_Orchestrator.py")


def _source() -> str:
    return PAGE.read_text(encoding="utf-8")


def _tree() -> ast.AST:
    return ast.parse(_source())


def _calls_symbol(tree: ast.AST, symbol: str) -> bool:
    return any(
        isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id == symbol
            or isinstance(node.func, ast.Attribute)
            and node.func.attr == symbol
        )
        for node in ast.walk(tree)
    )


def test_f51_page_wires_real_orchestrator_contract():
    source = _source()
    tree = _tree()
    for marker in (
        "QualityGatesPlan",
        "DeliveryRenderPlan",
        "VideoBaseRenderManifest",
        "ProductionOrchestratorRequest",
        "ProductionOrchestratorStatus",
        "build_production_orchestrator",
    ):
        assert marker in source
    assert _calls_symbol(tree, "model_validate")
    assert _calls_symbol(tree, "build_production_orchestrator")
    assert _calls_symbol(tree, "file_uploader")


def test_f51_page_never_fabricates_human_approval_or_downstream_completion():
    source = _source()
    assert "HumanReviewState.APPROVED" not in source
    assert "HumanReviewState.PENDING.value" in source
    assert "HumanReviewState.REJECTED.value" in source
    assert "F51 no acepta APPROVED como declaración" in source
    assert "plan.finalization_complete" in source
    assert "plan.publication_package_complete" in source
    assert "F51 no decide la aprobación" in source


def test_f51_page_preserves_orchestration_only_guardrails():
    source = _source()
    for marker in (
        "plan.orchestration_only",
        "plan.invokes_render",
        "plan.invokes_llm",
        "plan.invokes_network",
        "plan.writes_runtime_config",
        "plan.auto_publication",
        "plan.authorization_to_publish",
        "plan.uploads_files",
        "plan.webhook_calls",
        "plan.marks_published",
    ):
        assert marker in source
    assert "no renderiza, no aprueba revisión humana y no publica" in source
    assert "No ejecuta F6, F52 ni F53" in source


def test_f51_page_has_no_system_or_publication_side_effect_calls():
    tree = _tree()
    forbidden = {
        "system",
        "popen",
        "Popen",
        "check_call",
        "check_output",
        "unlink",
        "remove",
        "rmtree",
        "publish",
        "upload",
        "webhook",
    }
    called = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    assert called.isdisjoint(forbidden)
