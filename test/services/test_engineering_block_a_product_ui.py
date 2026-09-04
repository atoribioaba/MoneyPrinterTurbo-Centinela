from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PAGES = {
    "F16": ROOT / "webui/pages/16_Astronomy_Motion_Graphics.py",
    "F17": ROOT / "webui/pages/17_Cinematic_Infographics.py",
    "F18": ROOT / "webui/pages/18_Depth_Parallax.py",
    "F19": ROOT / "webui/pages/19_Color_Science.py",
    "F20": ROOT / "webui/pages/20_Shot_Matching.py",
}

SERVICE_BINDINGS = {
    "F16": ("app.services.astronomy_motion_graphics", "build_motion_graphics"),
    "F17": ("app.services.cinematic_infographics", "build_cinematic_infographics"),
    "F18": ("app.services.depth_parallax", "build_depth_parallax"),
    "F19": ("app.services.color_science", "build_color_science"),
    "F20": ("app.services.shot_matching", "build_shot_matching"),
}

PRODUCTIVE_ACTIONS = {
    "F16": "Planificar motion graphics",
    "F17": "Planificar infografías",
    "F18": "Planificar profundidad / parallax",
    "F19": "Generar plan de Color Science",
    "F20": "Analizar Shot Matching",
}


def _source(name: str) -> str:
    return PAGES[name].read_text(encoding="utf-8")


def _tree(name: str) -> ast.AST:
    return ast.parse(_source(name))


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


def test_block_a_pages_import_and_call_real_services():
    for name, (module, symbol) in SERVICE_BINDINGS.items():
        tree = _tree(name)
        assert _imports_symbol(tree, module, symbol), name
        assert _calls_symbol(tree, symbol), name


def test_block_a_pages_have_productive_actions_and_are_not_shell_only():
    old_shell = "Esta fase expone su contrato por API y artefactos JSON auditables"
    for name, action in PRODUCTIVE_ACTIONS.items():
        source = _source(name)
        assert action in source, name
        assert old_shell not in source, name


def test_block_a_pages_fail_closed_and_preserve_diagnostics():
    for name in PAGES:
        source = _source(name)
        assert "except Exception as exc:" in source, name
        assert 'st.expander("Detalles técnicos", expanded=False)' in source, name
        assert 'st.code(f"{type(exc).__name__}: {exc}", language=None)' in source, name
        assert "No se ha podido" in source, name
        assert "No se ha fabricado ningún resultado" in source or "No se ha inferido profundidad" in source or "No se han analizado frames nuevos" in source, name


def test_block_a_pages_are_mobile_safe_single_column():
    for name in PAGES:
        source = _source(name)
        assert "st.columns(" not in source, name
        assert "st.dataframe(" not in source, name


def test_f18_f19_f20_validate_real_upstream_models():
    f18 = _source("F18")
    f19 = _source("F19")
    f20 = _source("F20")

    assert "VisualStoryGraph.model_validate_json" in f18
    assert "SmartKenBurnsPlan.model_validate_json" in f18
    assert "DepthMapHint.model_validate" in f18
    assert "DepthParallaxRequest(" in f18

    assert "VisualStoryGraph.model_validate_json" in f19
    assert "DepthParallaxPlan.model_validate_json" in f19
    assert "ColorScienceRequest(" in f19

    assert "VisualStoryGraph.model_validate_json" in f20
    assert "ShotQualityPlan.model_validate_json" in f20
    assert "ColorSciencePlan.model_validate_json" in f20
    assert "ShotMatchingRequest(" in f20


def test_block_a_pages_present_real_result_fields():
    expected = {
        "F16": ("result.cue_count", "cue.normalized_start", "result.motion_graphics_hash"),
        "F17": ("result.card_count", "card.layout.value", "result.infographics_hash"),
        "F18": ("result.depth_map_ready_count", "scene.max_parallax_shift_fraction", "result.depth_parallax_hash"),
        "F19": ("result.grade_ready_count", "scene.profile.value", "result.color_science_hash"),
        "F20": ("result.match_ready_count", "edge.exposure_offset_ev", "result.shot_matching_hash"),
    }
    for name, markers in expected.items():
        source = _source(name)
        for marker in markers:
            assert marker in source, f"{name}: {marker}"


def test_block_a_pages_do_not_duplicate_backend_algorithms():
    forbidden = {
        "F18": ("max_parallax_shift_fraction=shift", "0.008 + 0.014"),
        "F19": ("_PROFILE =", "MYSTERIOUS_NEUTRAL_COOL, 0.92"),
        "F20": ("def _exposure_delta", "math.log2("),
    }
    for name, markers in forbidden.items():
        source = _source(name)
        for marker in markers:
            assert marker not in source, f"{name}: {marker}"


def test_block_a_introduces_no_publication_or_network_routes():
    forbidden = (
        "upload_file",
        "webhook",
        "mark_published",
        "authorization_to_publish",
        "requests.",
        "httpx.",
        "urllib.",
    )
    for name in PAGES:
        source = _source(name)
        for marker in forbidden:
            assert marker not in source, f"{name}: {marker}"
