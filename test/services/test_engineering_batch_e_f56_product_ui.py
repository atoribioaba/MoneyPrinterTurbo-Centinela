from __future__ import annotations

import ast
from pathlib import Path


PAGE = Path("webui/pages/56_Operational_Hardening.py")


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


def test_f56_page_wires_real_contract_in_memory():
    source = _source()
    tree = _tree()
    assert "OperationalEnvironmentSnapshot" in source
    assert "OperationalHardeningRequest" in source
    assert "OperationalHardeningStatus" in source
    assert "build_operational_hardening" in source
    assert _calls_symbol(tree, "model_validate")
    assert _calls_symbol(tree, "build_operational_hardening")
    assert _calls_symbol(tree, "file_uploader")


def test_f56_page_preserves_audit_only_boundary():
    source = _source()
    assert "no inspecciona el PC" in source
    assert "no ejecuta comandos del sistema" in source
    assert "No certifica por sí solo el estado físico actual del PC" in source
    assert "La verificación física" in source


def test_f56_page_has_no_system_probe_or_mutation_calls():
    tree = _tree()
    forbidden_names = {
        "system",
        "popen",
        "run",
        "Popen",
        "check_call",
        "check_output",
        "unlink",
        "remove",
        "rmtree",
    }
    called = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    assert called.isdisjoint(forbidden_names)


def test_f56_page_exposes_backend_findings_and_guardrails():
    source = _source()
    for marker in (
        "plan.safe_to_run_pipeline",
        "plan.block_count",
        "plan.warning_count",
        "plan.findings",
        "plan.operational_hardening_hash",
        "plan.audit_only",
        "plan.modifies_config",
        "plan.resets_network",
        "plan.deletes_files",
        "plan.downloads_dependencies",
        "plan.network_calls",
    ):
        assert marker in source
