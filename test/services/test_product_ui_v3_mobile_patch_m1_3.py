from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_m1_3_active_nav_normalizes_primary_button_typography() -> None:
    css = _read("webui/product/m1_2_patch.css")

    selector = (
        '.st-key-centinela-mobile-nav [class*="st-key-centinela-nav-"]'
        '[class*="-active"] .stButton > button'
    )
    assert selector in css
    assert "font-size: .58rem !important" in css
    assert "white-space: nowrap !important" in css
    assert "word-break: keep-all !important" in css


def test_m1_3_home_stack_targets_same_element_streamlit_shape() -> None:
    css = _read("webui/product/m1_2_patch.css")

    assert '.st-key-centinela-home-grid[data-testid="stHorizontalBlock"]' in css
    assert ".st-key-centinela-home-grid," in css
    assert "flex-direction: column !important" in css
    assert "flex-wrap: nowrap !important" in css
    assert "max-width: 100% !important" in css


def test_m1_3_create_submit_targets_keyed_form_itself() -> None:
    css = _read("webui/product/m1_2_patch.css")

    assert (
        '.st-key-create-video-v2[data-testid="stForm"] '
        '[data-testid="stFormSubmitButton"] button'
    ) in css
    assert "linear-gradient(135deg, #b9872f, var(--centinela-gold-primary))" in css
    assert "color: #151008 !important" in css


def test_m1_3_scope_remains_presentation_only() -> None:
    css = _read("webui/product/m1_2_patch.css")

    assert "VisualGenerationRequest" not in css
    assert "ProviderRuntimeState" not in css
    assert "ProductionSpine" not in css
    assert "AUTO_PUBLICATION" not in css
    assert "_future_only_events" not in css
