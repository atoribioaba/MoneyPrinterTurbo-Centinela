from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_product_sky_planner_sources_compile() -> None:
    for relative in (
        "webui/Centinela.py",
        "webui/product/sky_planner.py",
        "app/services/centinela/http_json.py",
        "app/services/centinela/sky_window_planner.py",
    ):
        compile(_read(relative), relative, "exec")


def test_canonical_cielo_route_uses_agenda_plus_observation_planner() -> None:
    shell = _read("webui/Centinela.py")
    planner = _read("webui/product/sky_planner.py")

    assert "sky_planner.sky_page" in shell
    assert "SKY_PAGE = studio.SKY_PAGE" not in shell
    assert 'url_path="cielo"' in shell
    assert "mobile_pages.ephemerides_page()" in planner
    assert "render_observation_planner(observer)" in planner


def test_manual_j2000_coordinates_are_never_promoted_to_verified_fact() -> None:
    planner = _read("webui/product/sky_planner.py")

    assert 'source_ids=["product-user-supplied-j2000"]' in planner
    assert "scientific_status=ScientificStatus.NO_VERIFICADO" in planner
    assert "NO VERIFICADO" in planner
    assert "ScientificStatus.HECHO_VERIFICADO" not in planner


def test_network_forecasts_require_explicit_submit_and_user_opt_in() -> None:
    planner = _read("webui/product/sky_planner.py")

    submitted_index = planner.index("if submitted:")
    weather_index = planner.index("fetch_open_meteo_snapshot(")
    astro_index = planner.index("fetch_7timer_astro_snapshots(")
    opt_in_index = planner.index("if use_forecasts:")

    assert weather_index > submitted_index
    assert astro_index > submitted_index
    assert weather_index > opt_in_index
    assert astro_index > opt_in_index
    assert "16 * 24" in planner
    assert "<= 72.0" in planner


def test_product_planner_preserves_sqm_and_bortle_evidence_semantics() -> None:
    planner = _read("webui/product/sky_planner.py")

    assert '"SQM medido"' in planner
    assert '"Bortle de mapa"' in planner
    assert '"Bortle estimado"' in planner
    assert "EvidenceKind.MEASURED" in planner
    assert "EvidenceKind.MAP_DERIVED" in planner
    assert "EvidenceKind.INFERRED" in planner
    assert "sqm_mag_arcsec2=float(sqm)" in planner
    assert "bortle_class=int(bortle)" in planner
    assert "sqm" not in planner.lower().split("bortle_class=int(bortle)")[1][:100]


def test_product_planner_is_guidance_not_publication_authority() -> None:
    planner = _read("webui/product/sky_planner.py")

    assert "INFERENCIA" in planner
    assert "No garantiza visibilidad ni calidad fotográfica" in planner
    for forbidden in (
        "media_publish",
        "upload_private",
        "upload_to_inbox",
        "AUTO_PUBLICATION=True",
        "approved=True",
    ):
        assert forbidden not in planner
