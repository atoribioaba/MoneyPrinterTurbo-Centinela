from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_product_navigation_routes_to_structured_review_page():
    text = (_repo_root() / "webui" / "Centinela.py").read_text(encoding="utf-8")
    compile(text, "webui/Centinela.py", "exec")
    assert "from webui.product import pages, review" in text
    assert "st.Page(review.review_page, title=\"Revisión\")" in text
    assert "st.Page(pages.review_page, title=\"Revisión\")" not in text


def test_structured_review_ui_exposes_all_seven_canonical_gates():
    text = (_repo_root() / "webui" / "product" / "review.py").read_text(encoding="utf-8")
    compile(text, "webui/product/review.py", "exec")
    for field in (
        "science_passed",
        "visual_passed",
        "audio_passed",
        "subtitles_passed",
        "rights_passed",
        "thumbnail_passed",
        "copy_passed",
    ):
        assert field in text
    assert "review.all_required_gates_passed" in text
    assert "HumanFinalReviewDecision.APPROVE" in text
    assert "HumanFinalReviewDecision.CHANGES_REQUESTED" in text
    assert "approved=True" not in text
    assert "approved=False" not in text


def test_structured_review_ui_preserves_manual_publication_boundary():
    text = (_repo_root() / "webui" / "product" / "review.py").read_text(encoding="utf-8")
    assert "No autoriza ni ejecuta publicación automática" in text
