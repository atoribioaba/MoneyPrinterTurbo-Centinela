from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from webui.product import mobile_patch_m1_1


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_m1_1_header_uses_hamburger_only_and_preserves_single_row_contract() -> None:
    source = _read("webui/Centinela.py")
    css = _read("webui/product/v3_patch.css")

    header = source.split('key="centinela-mobile-header"', 1)[1].split(
        'key="centinela-mobile-nav"', 1
    )[0]
    assert 'mobile_brand, mobile_menu = st.columns([9, 1]' in header
    assert '"☰"' in header
    assert '"Menú"' not in header
    assert "grid-template-columns: minmax(0, 1fr) 52px" in css
    assert "width: 44px !important" in css
    assert "text-overflow: ellipsis !important" in css


def test_m1_1_bottom_nav_has_exactly_one_explicit_active_state_path() -> None:
    source = _read("webui/Centinela.py")
    css = _read("webui/product/v3_patch.css")

    assert 'type="primary" if state == "active" else "secondary"' in source
    assert "def _more_is_active()" in source
    assert 'centinela-nav-mobile-more-{more_state}' in source
    assert "rgba(211, 163, 63, .18)" in css
    assert "#f1c76d" in css
    assert "-idle" in css
    assert "background: transparent !important" in css


def test_m1_1_mobile_stepper_is_compact_and_keeps_desktop_stepper() -> None:
    helper = _read("webui/product/mobile_patch_m1_1.py")
    css = _read("webui/product/v3_patch.css")

    assert "centinela-stepper-desktop" in helper
    assert "centinela-stepper-mobile" in helper
    assert "ETAPA {current_index + 1} DE {len(pipeline)}" in helper
    assert "Anterior:" in helper
    assert "Siguiente:" in helper
    assert ".centinela-stepper-desktop" in css
    assert "display: none !important" in css
    assert ".centinela-stepper-mobile" in css
    assert "overflow: hidden" in css


def test_m1_1_artifact_missing_is_product_safe_and_preserves_technical_evidence() -> None:
    helper = _read("webui/product/mobile_patch_m1_1.py")
    studio = _read("webui/product/studio.py")

    assert "No se ha podido materializar todavía el siguiente artefacto" in helper
    assert "La sección permanece detenida de forma segura" in helper
    assert 'with st.expander("Detalles técnicos"' in helper
    assert "type(exc).__name__" in helper
    assert "No se ha fabricado ningún artefacto" in helper
    assert "mobile_patch_m1_1.render_visual_generation_workspace(" in studio
    assert "visual_generation_module.render_visual_generation_workspace" in helper


def test_m1_1_expected_cloud_writer_room_block_is_explained_without_unlocking_pipeline() -> None:
    project = SimpleNamespace(
        state=SimpleNamespace(value="BLOCKED"),
        latest_jobs=(SimpleNamespace(message="SCRIPT: Writer Room iniciado"),),
    )

    copy = mobile_patch_m1_1.blocked_project_product_copy(project)

    assert copy is not None
    assert "detenido de forma segura en Guion" in copy
    assert "Ollama loopback" in copy
    assert "no se fabrica un guion" in copy
    assert "no se descarga ningún modelo" in copy


def test_m1_1_product_timestamp_is_human_spanish_and_raw_value_is_unchanged() -> None:
    raw = "2026-09-04T19:05:20.114314Z"

    rendered = mobile_patch_m1_1.product_datetime_es(raw)

    assert rendered == "4 sep 2026 · 21:05"
    assert ".114314" not in rendered
    assert raw == "2026-09-04T19:05:20.114314Z"

    aware = datetime(2026, 9, 4, 19, 5, 20, 114314, tzinfo=UTC)
    assert mobile_patch_m1_1.product_datetime_es(aware) == rendered


def test_m1_1_product_history_copy_removes_internal_prefixes_but_source_trace_is_kept() -> None:
    studio = _read("webui/product/studio.py")

    assert mobile_patch_m1_1.product_job_message("SCRIPT: Writer Room iniciado") == (
        "Writer Room iniciado"
    )
    assert mobile_patch_m1_1.product_job_message(
        "RESEARCH: advancing project state"
    ) == "Investigación actualizada"
    assert "product_job_message(" in studio
    assert "Traza interna preservada" in studio
    assert "job_type={job.job_type}" in studio
    assert "message={job.message or ''}" in studio
    assert "updated_at={job.updated_at}" in studio


def test_m1_1_create_primary_cta_is_gold_and_mobile_type_floor_is_present() -> None:
    css = _read("webui/product/v3_patch.css")

    assert ".st-key-create-video-v2" in css
    assert "linear-gradient(135deg, #b9872f, var(--centinela-gold-primary))" in css
    assert "color: #151008 !important" in css
    assert '[data-testid="stCaptionContainer"] p' in css
    assert "font-size: .79rem !important" in css
    assert "font-size: max(.875rem, 14px)" in css
    assert "font-size: .75rem" in css


def test_m1_1_does_not_modify_ai_contract_source_or_agenda_contract() -> None:
    helper = _read("webui/product/mobile_patch_m1_1.py")
    visual = _read("webui/product/visual_generation.py")
    agenda = _read("webui/product/mobile_pages.py")

    assert "VisualGenerationRequest" not in helper
    assert "ProviderRuntimeState" not in helper
    assert "allow_provider_fallback=False" in visual
    assert "AI_SCIENTIFIC_STATUS = ScientificVisualStatus.RECREACION_VISUAL" in visual
    assert "_future_only_events(stored_events, _agenda_now_utc(calendar))" in agenda
