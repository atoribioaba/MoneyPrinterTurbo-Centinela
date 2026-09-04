from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_m1_4_active_nav_targets_streamlit_primary_semantics() -> None:
    css = _read("webui/product/m1_2_patch.css")

    assert '.st-key-centinela-mobile-nav [data-testid="stBaseButton-primary"]' in css
    assert '.st-key-centinela-mobile-nav button[kind="primary"]' in css
    assert "white-space: nowrap !important" in css
    assert "word-break: keep-all !important" in css
    assert "overflow-wrap: normal !important" in css


def test_m1_4_active_nav_keeps_compact_mobile_typography() -> None:
    css = _read("webui/product/m1_2_patch.css")

    assert "font-size: .58rem !important" in css
    assert "padding-inline: .02rem !important" in css
    assert "line-height: 1.05 !important" in css


def test_m1_4_primary_form_submit_uses_gold_product_semantics() -> None:
    css = _read("webui/product/m1_2_patch.css")

    assert '[data-testid="stFormSubmitButton"] [data-testid="stBaseButton-primary"]' in css
    assert '[data-testid="stFormSubmitButton"] button[kind="primary"]' in css
    assert "linear-gradient(135deg, #b9872f, var(--centinela-gold-primary))" in css
    assert "color: #151008 !important" in css


def test_m1_4_scope_remains_presentation_only() -> None:
    css = _read("webui/product/m1_2_patch.css")

    assert "VisualGenerationRequest" not in css
    assert "ProviderRuntimeState" not in css
    assert "ProductionSpine" not in css
    assert "AUTO_PUBLICATION" not in css
    assert "_future_only_events" not in css
