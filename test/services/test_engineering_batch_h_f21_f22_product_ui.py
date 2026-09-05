from __future__ import annotations

import ast
from pathlib import Path


PAGES = {
    21: Path("webui/pages/21_Transition_Director.py"),
    22: Path("webui/pages/22_Sound_Design.py"),
}


def _source(number: int) -> str:
    return PAGES[number].read_text(encoding="utf-8")


def _tree(number: int) -> ast.AST:
    return ast.parse(_source(number))


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


def test_f21_wires_real_transition_contract():
    source = _source(21)
    tree = _tree(21)
    for marker in (
        "VisualStoryGraph",
        "ShotMatchingPlan",
        "TransitionDirectorRequest",
        "build_transition_director",
        "TransitionStatus.PLACEHOLDER_PENDING_MEDIA",
    ):
        assert marker in source
    assert _calls_symbol(tree, "model_validate")
    assert _calls_symbol(tree, "build_transition_director")


def test_f21_keeps_restrained_planning_only_boundary():
    source = _source(21)
    for marker in (
        "plan.planning_only",
        "plan.uses_llm",
        "plan.gpu_required",
        "plan.renders_video",
        "plan.creates_flashy_transitions",
        "plan.searches_assets",
        "plan.auto_publication",
    ):
        assert marker in source
    assert "evita transiciones gratuitas" in source
    assert "F21 sólo produce un plan" in source


def test_f22_wires_real_sound_design_contract():
    source = _source(22)
    tree = _tree(22)
    for marker in (
        "VisualStoryGraph",
        "CinematicInfographicsPlan",
        "TransitionDirectorPlan",
        "SoundDesignRequest",
        "build_sound_design",
    ):
        assert marker in source
    assert _calls_symbol(tree, "model_validate")
    assert _calls_symbol(tree, "build_sound_design")


def test_f22_never_fabricates_assets_licenses_or_space_sound():
    source = _source(22)
    assert "LICENCIA_NO_VERIFICADA" in source
    assert "no selecciona assets y no inventa licencias" in source
    assert "cue.asset_selected" in source
    assert "cue.requires_human_selection" in source
    assert "cue.diegetic_space_sound" in source


def test_f22_preserves_planning_only_audio_guardrails():
    source = _source(22)
    for marker in (
        "plan.planning_only",
        "plan.uses_llm",
        "plan.gpu_required",
        "plan.renders_audio",
        "plan.generates_audio",
        "plan.downloads_audio",
        "plan.searches_audio",
        "plan.selects_assets",
        "plan.verifies_external_licenses",
        "plan.auto_publication",
    ):
        assert marker in source


def test_f21_f22_have_no_system_or_media_execution_calls():
    forbidden = {
        "system",
        "popen",
        "Popen",
        "check_call",
        "check_output",
        "unlink",
        "remove",
        "rmtree",
        "render",
        "download",
        "publish",
    }
    for number in PAGES:
        called = set()
        for node in ast.walk(_tree(number)):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
        assert called.isdisjoint(forbidden)
