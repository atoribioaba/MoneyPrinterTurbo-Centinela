from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_acceptance_patch_loads_after_base_styles() -> None:
    source = _read("webui/Centinela.py")
    assert '("styles.css", "v3_patch.css")' in source
    assert "v3_patch.css" in source


def test_primary_navigation_uses_selected_page_and_switch_page() -> None:
    source = _read("webui/Centinela.py")
    assert "def _page_is_active" in source
    assert "def _nav_button" in source
    assert 'state = "active" if _page_is_active(target) else "idle"' in source
    assert "st.switch_page(target)" in source
    for slot in (
        "desktop-home",
        "desktop-create",
        "desktop-projects",
        "desktop-review",
        "mobile-home",
        "mobile-create",
        "mobile-projects",
        "mobile-review",
    ):
        assert f'slot="{slot}"' in source


def test_product_headers_are_home_cinematic_and_work_screens_compact() -> None:
    source = _read("webui/product/ui.py")
    assert 'is_home = eyebrow.strip().upper().startswith("INICIO")' in source
    assert "centinela-work-header" in source
    assert "centinela-hero--home" in source
    assert "centinela-brand-mark__scope" in source
    assert "centinela-brand-mark__stand" in source


def test_review_is_preview_first_and_has_single_empty_state_path() -> None:
    source = _read("webui/product/review.py")
    assert 'project = ui.select_project(service, "review-selector")' in source
    assert 'pages._project_selector(service, "review-selector")' not in source
    assert source.index("_render_review_preview(service, project)") < source.index(
        'key="centinela-review-context"'
    )
    assert '"Crear una historia"' in source
    assert 'key="centinela-review-actions"' in source
    assert "review.all_required_gates_passed" in source


def test_publication_uses_quiet_selector_and_manual_policy_is_unchanged() -> None:
    source = _read("webui/product/publication.py")
    assert 'project = ui.select_project(service, "publication-selector")' in source
    assert 'pages._project_selector(service, "publication-selector")' not in source
    assert '"Ir a Proyectos"' in source
    assert "AUTO_PUBLICATION=FALSE" in source
    assert "MANUAL_PUBLICATION_ONLY=TRUE" in source
    assert "AUTHORIZATION_TO_PUBLISH=FALSE" in source
    assert "Publicar ahora" not in source


def test_acceptance_css_has_active_navigation_and_mobile_work_header() -> None:
    css = _read("webui/product/v3_patch.css")
    assert '[class*="st-key-centinela-nav-"][class*="-active"]' in css
    assert ".centinela-work-header" in css
    assert ".centinela-brand-mark" in css
    assert "@media (max-width: 700px)" in css
    assert "min-height: 50px" in css
