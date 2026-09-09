from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_small_body_product_module_compiles() -> None:
    relative = "webui/product/small_body_planner.py"
    source = _read(relative)
    compile(source, relative, "exec")


def test_canonical_sky_page_wires_manual_small_body_planner() -> None:
    source = _read("webui/product/sky_planner.py")
    assert "render_small_body_planner" in source
    assert "render_observation_planner(observer)" in source
    assert "render_small_body_planner(observer)" in source


def test_horizons_product_lookup_is_manual_and_has_no_publication_or_polling() -> None:
    source = _read("webui/product/small_body_planner.py")
    assert '"Consultar JPL Horizons"' in source
    assert "fetch_horizons_observer_result" in source
    assert "SmallBodyObserverRequest" in source
    assert "La consulta sólo se realiza cuando pulsas" in source

    forbidden = (
        "st.autorefresh",
        "while True",
        "time.sleep(",
        "publish(",
        "publication",
        "AUTO_PUBLICATION=TRUE",
    )
    for token in forbidden:
        assert token not in source


def test_horizons_result_keeps_provenance_and_does_not_rename_scientific_columns() -> None:
    source = _read("webui/product/small_body_planner.py")
    assert "for label, value in result.columns.items()" in source
    assert "provenance.api_version" in source
    assert "provenance.target_command" in source
    assert "provenance.query_time_utc" in source
    assert "provenance.retrieved_at_utc" in source
    assert "provenance.result_sha256" in source
    assert "FactLock" in source
    assert "revisión humana" in source


def test_horizons_cached_result_is_invalidated_when_observer_changes() -> None:
    source = _read("webui/product/small_body_planner.py")
    assert '"observer": observer.model_dump(mode="json")' in source
    assert 'state.get("observer") != observer.model_dump(mode="json")' in source
    assert "La ubicación del observador ha cambiado" in source
