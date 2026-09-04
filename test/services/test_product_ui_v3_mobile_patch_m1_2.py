from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_m1_2_bottom_nav_labels_are_mobile_safe_without_mid_word_breaks() -> None:
    css = _read("webui/product/m1_2_patch.css")

    assert "@media (max-width: 430px)" in css
    assert "flex-direction: column !important" in css
    assert "white-space: nowrap !important" in css
    assert "word-break: keep-all !important" in css
    assert "overflow-wrap: normal !important" in css
    assert "hyphens: none !important" in css


def test_m1_2_home_command_center_stacks_on_narrow_mobile() -> None:
    css = _read("webui/product/m1_2_patch.css")

    assert ".st-key-centinela-home-grid" in css
    assert 'grid-template-columns' not in css.split(".st-key-centinela-home-grid", 1)[1].split("}", 2)[0]
    assert "flex-direction: column !important" in css
    assert "width: 100% !important" in css


def test_m1_2_create_submit_is_gold_without_destructive_red_semantics() -> None:
    css = _read("webui/product/m1_2_patch.css")

    assert '.st-key-create-video-v2 [data-testid="stFormSubmitButton"] button' in css
    assert "linear-gradient(135deg, #b9872f, var(--centinela-gold-primary))" in css
    assert "color: #151008 !important" in css
    assert "#ff0000" not in css.casefold()


def test_m1_2_review_uses_human_product_timestamp_and_keeps_trace_elsewhere() -> None:
    review = _read("webui/product/review.py")
    studio = _read("webui/product/studio.py")

    assert "mobile_patch_m1_1.product_datetime_es(project.updated_at)" in review
    assert 'st.caption(f"Actualizado: {project.updated_at}")' not in review
    assert "st.code(str(project.updated_at), language=None)" in studio


def test_m1_2_css_overlay_is_loaded_after_certified_m1_styles() -> None:
    helper = _read("webui/product/mobile_patch_m1_1.py")
    shell = _read("webui/Centinela.py")

    assert '_M1_2_STYLE_PATH = Path(__file__).with_name("m1_2_patch.css")' in helper
    assert "_M1_2_STYLE_PATH.read_text" in helper
    assert 'for style_name in ("styles.css", "v3_patch.css")' in shell
    assert "mobile_patch_m1_1.install_ui_overrides(ui)" in shell


def test_m1_2_scope_does_not_reopen_agenda_ai_or_publication_contracts() -> None:
    helper = _read("webui/product/mobile_patch_m1_1.py")
    css = _read("webui/product/m1_2_patch.css")

    combined = helper + css
    assert "VisualGenerationRequest" not in combined
    assert "ProviderRuntimeState" not in combined
    assert "AUTO_PUBLICATION" not in combined
    assert "_future_only_events" not in combined
