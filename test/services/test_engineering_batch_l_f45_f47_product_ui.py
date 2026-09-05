from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGES = {
    "f45": ROOT / "webui/pages/45_Policy_Registry.py",
    "f46": ROOT / "webui/pages/46_Shadow_Policy_Evaluator.py",
    "f47": ROOT / "webui/pages/47_Canary_Policy_Planner.py",
}


def _source(name: str) -> str:
    return PAGES[name].read_text(encoding="utf-8")


def _tree(name: str) -> ast.AST:
    return ast.parse(_source(name))


def _imports(name: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_tree(name)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names.add(module)
            names.update(alias.name for alias in node.names)
    return names


def _calls(name: str) -> list[ast.Call]:
    return [node for node in ast.walk(_tree(name)) if isinstance(node, ast.Call)]


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        if isinstance(call.func.value, ast.Name):
            return f"{call.func.value.id}.{call.func.attr}"
        return call.func.attr
    return None


def _button_labels(name: str) -> list[str]:
    labels: list[str] = []
    for call in _calls(name):
        if _call_name(call) != "st.button" or not call.args:
            continue
        arg = call.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            labels.append(arg.value)
    return labels


def test_batch_l_pages_parse_and_use_real_service_wiring():
    expected = {
        "f45": (
            {"PolicyRegistryRequest", "PolicyRegistryPlan", "build_policy_registry"},
            "PolicyRegistryRequest",
            "build_policy_registry",
        ),
        "f46": (
            {"ShadowPolicyRequest", "ShadowPolicyPlan", "build_shadow_policy_plan"},
            "ShadowPolicyRequest",
            "build_shadow_policy_plan",
        ),
        "f47": (
            {"CanaryPolicyRequest", "CanaryPolicyPlan", "build_canary_policy_plan"},
            "CanaryPolicyRequest",
            "build_canary_policy_plan",
        ),
    }
    for name, (required, request_name, service_name) in expected.items():
        tree = _tree(name)
        compile(tree, str(PAGES[name]), "exec")
        imports = _imports(name)
        called = {_call_name(call) for call in _calls(name)}
        assert required <= imports
        assert request_name in called
        assert service_name in called


def test_f45_consumes_f44_evidence_without_alternative_approval_ui():
    source = _source("f45")
    imports = _imports("f45")
    labels = {label.lower() for label in _button_labels("f45")}
    assert "HumanPolicyApprovalPlan" in imports
    assert "PolicyCandidatePlan" in imports
    assert "PreviousPolicyReference" in imports
    assert "Preparar registro de política" in _button_labels("f45")
    assert not any("aprobar" in label or "rechazar" in label for label in labels)
    assert "st.text_input" not in source
    assert "st.text_area" not in source
    assert "approval_record_hash" in source
    assert "source_human_policy_approval_hash" in source
    assert "NOT CRYPTOGRAPHICALLY RECOMPUTED BY F45" in source
    assert "ACTIVE =" in source
    assert "writes_runtime_config" in source
    assert "database_writes" in source
    assert "activates_policy" in source


def test_f46_uses_registry_and_policy_simulation_cases_not_f42_plan():
    source = _source("f46")
    imports = _imports("f46")
    assert "PolicyRegistryPlan" in imports
    assert "PolicySimulationCase" in imports
    assert "PolicySimulatorPlan" not in imports
    assert "Preparar evaluación shadow" in _button_labels("f46")
    assert "ShadowPolicyRequest" in imports
    assert "build_shadow_policy_plan" in imports
    assert "baseline mismatch" in source.lower()
    assert "shadow_only" in source
    assert "uses_real_cinematic_director" in source
    assert "runtime_effect" in source
    assert "renders_video" in source
    assert "gpu_required" in source


def test_f47_delegates_exposure_and_eligibility_to_real_model_and_service():
    source = _source("f47")
    imports = _imports("f47")
    assert "CanaryPolicyRequest" in imports
    assert "CanaryPolicyPlan" in imports
    assert "ShadowPolicyPlan" in imports
    assert "build_canary_policy_plan" in imports
    assert "Preparar plan canary" in _button_labels("f47")
    number_calls = [
        call for call in _calls("f47") if _call_name(call) == "st.number_input"
    ]
    assert len(number_calls) == 1
    keyword_names = {item.arg for item in number_calls[0].keywords}
    assert "min_value" not in keyword_names
    assert "max_value" not in keyword_names
    assert "0.01" in source
    assert "0.10" in source
    assert "structural_safe" in source
    assert "behavior_changed" in source
    assert "requires_human_launch" in source
    assert "candidate.launched" in source
    assert "plan.executes_canary" in source


def test_f47_has_no_launch_or_f48_action():
    labels = {label.lower() for label in _button_labels("f47")}
    source = _source("f47")
    assert not any(
        phrase in label
        for label in labels
        for phrase in ("lanzar", "activar canary", "deploy canary", "apply exposure")
    )
    assert "CanaryObservation" in source  # explanatory boundary text only
    assert "human_launch_confirmed" not in source
    assert "canary_monitor" not in source
    assert "build_canary_monitor" not in source


def test_product_ui_is_mobile_safe_and_fail_closed():
    for name in PAGES:
        source = _source(name)
        assert "st.columns" not in source
        assert "st.dataframe" not in source
        assert "st.table" not in source
        assert 'st.expander("Detalles técnicos"' in source
        assert "st.file_uploader" in source
        assert 'type="primary"' in source
        assert "st.error" in source
        assert "subprocess" not in _imports(name)
        assert "requests" not in _imports(name)
        assert "httpx" not in _imports(name)


def test_batch_l_has_zero_f48_runtime_wiring():
    for name in PAGES:
        imports = _imports(name)
        source = _source(name)
        assert "app.models.canary_monitor" not in imports
        assert "app.services.canary_monitor" not in imports
        assert "build_canary_monitor" not in source
        assert "human_launch_confirmed" not in source


def test_primary_actions_match_planning_boundaries():
    assert _button_labels("f45") == ["Preparar registro de política"]
    assert _button_labels("f46") == ["Preparar evaluación shadow"]
    assert _button_labels("f47") == ["Preparar plan canary"]
