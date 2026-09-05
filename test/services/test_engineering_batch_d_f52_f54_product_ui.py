from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGES = {
    "f52": ROOT / "webui" / "pages" / "52_Video_Base_E2E.py",
    "f53": ROOT / "webui" / "pages" / "53_Finalization_E2E.py",
    "f54": ROOT / "webui" / "pages" / "54_Publication_Package.py",
}


def _source(key: str) -> str:
    return PAGES[key].read_text(encoding="utf-8")


def _tree(key: str) -> ast.AST:
    return ast.parse(_source(key))


def _calls_symbol(tree: ast.AST, symbol: str) -> bool:
    return any(
        (
            isinstance(node.func, ast.Name)
            and node.func.id == symbol
        )
        or (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == symbol
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    )


def _imported_symbols(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_f52_wires_real_contract_without_local_side_effects():
    source = _source("f52")
    tree = _tree("f52")
    imported = _imported_symbols(tree)
    assert {
        "ProductionOrchestratorPlan",
        "VideoBaseRenderManifest",
        "VideoArtifactProbe",
        "VideoBaseE2ERequest",
        "build_video_base_e2e",
    } <= imported
    assert _calls_symbol(tree, "build_video_base_e2e")
    assert "subprocess" not in imported
    assert "os" not in imported
    assert not _calls_symbol(tree, "system")
    assert not _calls_symbol(tree, "Popen")
    assert "st.video" not in source
    assert "no inspecciona el filesystem" in source
    assert "no demuestra por sí sola que el archivo físico exista" in source
    assert "Auto publication" in source


def test_f53_consumes_existing_human_review_and_preserves_publication_boundary():
    source = _source("f53")
    tree = _tree("f53")
    imported = _imported_symbols(tree)
    assert {
        "VideoBaseE2EPlan",
        "HumanFinalReviewRecord",
        "FinalVideoArtifactProbe",
        "FinalizationE2ERequest",
        "build_finalization_e2e",
    } <= imported
    assert _calls_symbol(tree, "build_finalization_e2e")
    assert "HumanFinalReviewDecision" not in imported
    assert "datetime" not in imported
    assert "st.checkbox" not in source
    assert "no crea una aprobación paralela" in source
    assert "Authorization to publish" in source
    assert "Uploads files" in source
    assert "Webhook calls" in source
    assert "Marks published" in source
    assert "Auto publication" in source


def test_f54_is_planning_only_and_never_materializes_or_publishes():
    source = _source("f54")
    tree = _tree("f54")
    imported = _imported_symbols(tree)
    assert {
        "FinalizationE2EPlan",
        "PublicationMetadata",
        "PublicationPackageRequest",
        "PublicationSupportManifest",
        "build_publication_package",
    } <= imported
    assert _calls_symbol(tree, "build_publication_package")
    assert "write_text" not in source
    assert "write_bytes" not in source
    assert "shutil" not in imported
    assert "subprocess" not in imported
    assert "schedule_publication" not in source
    assert "Planning only" in source
    assert "Manual publication only" in source
    assert "Writes files" in source
    assert "Authorization to publish" in source
    assert "Marks published" in source
    assert "Auto publication" in source


def test_batch_d_does_not_call_f45_or_gpu_or_model_runtimes():
    combined = "\n".join(_source(key) for key in PAGES)
    forbidden = (
        "controlled_promotion_gate",
        "build_controlled_promotion",
        "torch.",
        "cuda",
        "ollama",
        "transformers",
        "download_model",
    )
    for marker in forbidden:
        assert marker.casefold() not in combined.casefold(), marker
