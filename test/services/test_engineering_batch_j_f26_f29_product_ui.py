from __future__ import annotations

import ast
from pathlib import Path


PAGES = {
    "f26": Path("webui/pages/26_Selective_Upscaling.py"),
    "f27": Path("webui/pages/27_Media_Mining.py"),
    "f28": Path("webui/pages/28_Quality_Comparator.py"),
    "f29": Path("webui/pages/29_Quality_Gates.py"),
}


def _source(key: str) -> str:
    return PAGES[key].read_text(encoding="utf-8")


def _tree(key: str) -> ast.AST:
    return ast.parse(_source(key))


def _called_symbols(tree: ast.AST) -> set[str]:
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    return called


def _imported_symbols(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_f26_wires_real_contract_and_preserves_ab_boundary():
    source = _source("f26")
    tree = _tree("f26")
    imported = _imported_symbols(tree)
    called = _called_symbols(tree)
    assert {
        "VideoBasePlan",
        "ShotQualityPlan",
        "SelectiveUpscalingRequest",
        "UpscaleSceneStatus",
        "build_selective_upscaling",
    } <= imported
    assert "build_selective_upscaling" in called
    assert "A_B_REVIEW_REQUIRED" in source
    assert "astronomy_fidelity_review_required" in source
    assert "plan.model_weights_license" in source
    assert "NO_VERIFICADA" not in source or "plan.model_weights_license" in source
    assert "No se ha ejecutado ningún upscale" in source


def test_f26_has_zero_runtime_surface():
    source = _source("f26")
    called = _called_symbols(_tree("f26"))
    for marker in (
        "plan.runs_upscaler",
        "plan.downloads_models",
        "plan.gpu_required",
        "plan.renders_video",
        "plan.invents_astronomy_detail",
    ):
        assert marker in source
    forbidden_calls = {
        "Popen",
        "system",
        "run",
        "check_call",
        "check_output",
        "download",
        "download_model",
        "cuda",
        "upscale",
    }
    assert called.isdisjoint(forbidden_calls)


def test_f27_wires_real_contract_without_detection_or_asset_side_effects():
    source = _source("f27")
    tree = _tree("f27")
    imported = _imported_symbols(tree)
    called = _called_symbols(tree)
    assert {
        "ShotQualityPlan",
        "MediaMiningRequest",
        "MediaMiningStatus",
        "build_media_mining",
    } <= imported
    assert "build_media_mining" in called
    for marker in (
        "VIDEO_DETECTION_REQUIRED",
        "plan.scenedetect_invocations",
        "plan.analyzes_video",
        "plan.splits_video",
        "plan.modifies_sources",
        "External asset search: false",
        "Asset selection: false",
    ):
        assert marker in source
    assert called.isdisjoint({"detect", "split", "download", "search", "requests", "post"})


def test_f28_wires_real_comparator_and_never_selects_winner():
    source = _source("f28")
    tree = _tree("f28")
    imported = _imported_symbols(tree)
    called = _called_symbols(tree)
    assert {
        "ShotQualityPlan",
        "SelectiveUpscalingPlan",
        "MediaMiningPlan",
        "QualityComparatorRequest",
        "QualityComparisonStatus",
        "build_quality_comparator",
    } <= imported
    assert "build_quality_comparator" in called
    assert "A_B_COMPARISON_REQUIRED" in source
    assert "HUMAN REVIEW REQUIRED" in source
    assert "Ganador: ninguno" in source
    assert "plan.selects_winner" in source
    assert "plan.modifies_media" in source
    assert called.isdisjoint({"select_winner", "choose_winner", "rank_winner", "modify_media"})


def test_f29_wires_real_quality_gates_and_shows_blocked_truthfully():
    source = _source("f29")
    tree = _tree("f29")
    imported = _imported_symbols(tree)
    called = _called_symbols(tree)
    assert {
        "QualityComparatorPlan",
        "SoundDesignPlan",
        "VoiceStudioPlan",
        "AudioMasteringPlan",
        "SubtitleIntelligencePlan",
        "QualityGatesRequest",
        "QualityGateStatus",
        "build_quality_gates",
    } <= imported
    assert "build_quality_gates" in called
    assert "QualityGateStatus.BLOCKED" in source
    assert "No se fabrica readiness" in source
    assert "READY_FOR_HUMAN_REVIEW" in source
    assert "Esto NO es aprobación humana ni autorización para publicar" in source
    assert "plan.human_approval_required" in source
    assert "plan.auto_publication" in source


def test_f29_never_creates_publication_or_human_approval_side_effects():
    source = _source("f29")
    called = _called_symbols(_tree("f29"))
    for marker in (
        "HUMAN_APPROVAL_REQUIRED",
        "authorization_to_publish",
        "Uploads files: 0",
        "Webhook calls: 0",
        "Marks published: false",
    ):
        assert marker in source
    forbidden = {
        "publish",
        "upload",
        "post",
        "webhook",
        "mark_published",
        "HumanFinalReviewRecord",
        "HumanPromotionDecision",
    }
    assert called.isdisjoint(forbidden)


def test_batch_j_pages_are_mobile_safe_fail_closed_and_do_not_duplicate_runtime():
    desktop_only = {"columns", "dataframe", "table"}
    runtime_forbidden = {
        "system",
        "Popen",
        "run",
        "check_call",
        "check_output",
        "ffmpeg",
        "ffprobe",
        "cuda",
        "download",
        "transcribe",
        "upload",
        "publish",
        "post",
    }
    for key in PAGES:
        source = _source(key)
        called = _called_symbols(_tree(key))
        assert "type=\"primary\"" in source
        assert "Detalles técnicos" in source
        assert "except Exception as exc" in source
        assert called.isdisjoint(desktop_only)
        assert called.isdisjoint(runtime_forbidden)


def test_batch_j_scope_contains_no_f30_f57_or_policy_runtime_calls():
    combined = "\n".join(_source(key) for key in PAGES)
    for marker in (
        "build_delivery_render",
        "build_policy_registry",
        "build_shadow_policy_plan",
        "build_controlled_promotion_plan",
        "build_golden",
        "torch.",
        "ollama",
        "transformers",
    ):
        assert marker not in combined
