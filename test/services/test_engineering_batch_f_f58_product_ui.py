from __future__ import annotations

import ast
from pathlib import Path


PAGE = Path("webui/pages/58_V1_Readiness_Audit.py")


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


def test_f58_page_wires_real_final_audit_contract():
    source = _source()
    tree = _tree()
    for marker in (
        "ProductionOrchestratorPlan",
        "PublicationPackagePlan",
        "AnalyticsImportPlan",
        "OperationalHardeningPlan",
        "GoldenE2ECertificationPlan",
        "OSSAuditEntry",
        "V1ReadinessRequest",
        "build_v1_readiness_audit",
    ):
        assert marker in source
    assert _calls_symbol(tree, "build_v1_readiness_audit")
    assert _calls_symbol(tree, "model_validate")


def test_f58_page_keeps_f57_real_golden_as_mandatory_input():
    source = _source()
    assert "F57 · GoldenE2ECertificationPlan JSON" in source
    assert "F57 sigue siendo evidencia real obligatoria" in source
    assert "Golden sintético no es aceptable" in source
    assert "CERTIFICATION_PASS" in source


def test_f58_human_freeze_approval_is_explicit_and_default_false():
    source = _source()
    assert "value=False" in source
    assert 'confirmation.strip() == "AUTORIZAR FREEZE V1"' in source
    assert "human_freeze_approval=human_freeze_approval" in source
    assert "Por defecto no existe autorización" in source


def test_f58_never_executes_or_mutates_architecture():
    source = _source()
    tree = _tree()
    for marker in (
        "plan.freeze_authorized",
        "plan.architecture_v1_frozen",
        "plan.freeze_executed",
        "plan.auto_publication",
        "plan.auto_activation",
        "plan.writes_runtime_config",
        "F58 NO ejecuta el freeze",
    ):
        assert marker in source

    forbidden = {
        "system",
        "popen",
        "Popen",
        "check_call",
        "check_output",
        "unlink",
        "remove",
        "rmtree",
        "update_file",
        "update_ref",
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
