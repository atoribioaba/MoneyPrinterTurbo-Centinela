from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_product_ui_v3_python_sources_compile() -> None:
    for relative in (
        "webui/Centinela.py",
        "webui/product/ui.py",
        "webui/product/studio.py",
        "webui/product/visual_generation.py",
        "webui/product/review.py",
        "webui/product/publication.py",
    ):
        source = _read(relative)
        compile(source, relative, "exec")


def test_reference_design_tokens_use_gold_for_primary_action_and_blue_for_progress() -> None:
    css = _read("webui/product/styles.css")
    assert "--centinela-bg-primary:" in css
    assert "--centinela-surface:" in css
    assert "--centinela-text-primary:" in css
    assert "--centinela-gold-primary:" in css
    assert "--centinela-gold-hover:" in css
    assert "--centinela-blue-progress:" in css
    assert "--centinela-green-success:" in css
    assert "--centinela-amber-warning:" in css
    assert "--centinela-red-error:" in css
    assert "button[kind=\"primary\"]" in css
    assert "var(--centinela-gold-primary)" in css


def test_product_shell_has_desktop_rail_mobile_header_and_five_action_bottom_nav() -> None:
    source = _read("webui/Centinela.py")
    assert 'key="centinela-desktop-nav"' in source
    assert 'key="centinela-mobile-header"' in source
    assert 'key="centinela-mobile-nav"' in source
    for label in ("Inicio", "Crear", "Proyectos", "Revisión"):
        assert f'label="{label}"' in source
    assert '"Más"' in source
    for secondary in ("Publicación manual", "Cielo", "Medios", "Sistema", "Ingeniería"):
        assert f'label="{secondary}"' in source


def test_mobile_css_covers_tablet_700_390_and_360_without_horizontal_overflow() -> None:
    css = _read("webui/product/styles.css")
    assert "overflow-x: hidden;" in css
    assert "@media (min-width: 701px) and (max-width: 1099px)" in css
    assert "@media (max-width: 700px)" in css
    assert "@media (max-width: 390px)" in css
    assert "@media (max-width: 360px)" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "min-height: 44px" in css
    assert "min-height: 48px" in css


def test_home_and_create_follow_reference_product_hierarchy_without_fake_data() -> None:
    source = _read("webui/product/studio.py")
    assert "Bienvenido al observatorio." in source
    assert "Todo listo para crear historias del Universo." in source
    assert "PRODUCCIÓN EN CURSO" in source
    assert "PRÓXIMO EVENTO" in source
    assert "PRODUCCIONES RECIENTES" in source
    assert "Agenda aún no calculada" in source
    assert "¿Cómo quieres empezar?" in source
    assert "Agenda futura" in source
    assert "Idea propia" in source
    assert "Proyecto existente" in source
    assert "Generar investigación y guion" in source
    assert "Reel / TikTok / Short" in source
    assert '"9:16"' in source
    assert '"30 fps"' in source


def test_visual_generation_uses_product_copy_and_preserves_fail_closed_contract() -> None:
    source = _read("webui/product/visual_generation.py")
    assert "RECREACIÓN VISUAL" in source
    assert "Texto → imagen" in source
    assert "Imagen → vídeo" in source
    assert "Texto → vídeo" in source
    assert "Generar imagen" in source
    assert "Generar vídeo" in source
    assert "Generación local pendiente de certificación" in source
    assert "Próximamente / runtime no disponible" in source
    assert "No existe CTA operativo." in source
    assert "Todavía no hay visuales generados para esta escena." in source
    assert "Usar en esta escena" in source
    assert "Animar para vídeo" in source
    assert "allow_provider_fallback=False" in source
    assert "if not state.ready:" in source
    assert "st.columns(" not in source


def test_runtime_flags_are_secondary_not_primary_copy() -> None:
    source = _read("webui/product/visual_generation.py")
    ui_source = _read("webui/product/ui.py")
    assert "render_runtime_status_card" in source
    assert "Detalles técnicos del motor" in ui_source
    assert "Motor habilitado" in ui_source
    assert "Adaptador" in ui_source
    assert "Pesos" in ui_source
    assert "Hardware" in ui_source
    assert "hardware_certified=False" not in source
    assert "weights_available=False" not in source


def test_visual_stepper_matches_product_pipeline_language() -> None:
    source = _read("webui/product/ui.py")
    for label in (
        "Investigación",
        "Guion",
        "Medios",
        "Voz",
        "Vídeo",
        "Revisión",
        "Publicación",
    ):
        assert f'("{label}",' in source
    assert "centinela-stepper" in source


def test_review_preserves_structured_7_of_7_and_real_preview_empty_state() -> None:
    source = _read("webui/product/review.py")
    assert "Preview final" in source
    assert "Preview aún no disponible" in source
    for label in (
        "1 · Rigor científico",
        "2 · Imagen y montaje visual",
        "3 · Audio y locución",
        "4 · Subtítulos",
        "5 · Derechos y licencias",
        "6 · Miniatura",
        "7 · Título, caption y textos",
    ):
        assert label in source
    assert "review.all_required_gates_passed" in source
    assert "No autoriza ni ejecuta publicación automática" in source


def test_publication_remains_manual_and_never_exposes_publish_now() -> None:
    source = _read("webui/product/publication.py")
    ui_source = _read("webui/product/ui.py")
    combined = source + ui_source
    assert "PUBLICACIÓN MANUAL" in combined
    assert "El Centinela prepara los archivos. Tú decides cuándo y dónde publicarlos." in combined
    assert '"Preparar paquete"' in source
    assert "Publicar ahora" not in combined
    assert "AUTO_PUBLICATION=FALSE" in source
    assert "MANUAL_PUBLICATION_ONLY=TRUE" in source
