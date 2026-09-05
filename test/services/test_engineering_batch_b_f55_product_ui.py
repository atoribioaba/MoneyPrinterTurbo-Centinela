from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.models.analytics_brain import AnalyticsPlatform
from app.models.analytics_import_adapter import (
    AnalyticsImportFormat,
    AnalyticsImportRequest,
    AnalyticsImportStatus,
)
from app.services.analytics_import_adapter import AnalyticsImportError, build_analytics_import


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "webui/pages/55_Analytics_Import_Adapter.py"


def _source() -> str:
    return PAGE.read_text(encoding="utf-8")


def _tree() -> ast.AST:
    return ast.parse(_source())


def _imports_symbol(tree: ast.AST, module: str, symbol: str) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == module
        and any(alias.name == symbol for alias in node.names)
        for node in ast.walk(tree)
    )


def _calls_symbol(tree: ast.AST, symbol: str) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == symbol
        for node in ast.walk(tree)
    )


def test_f55_page_imports_and_calls_real_contract():
    tree = _tree()
    assert _imports_symbol(tree, "app.models.analytics_import_adapter", "AnalyticsImportRequest")
    assert _imports_symbol(tree, "app.services.analytics_import_adapter", "AnalyticsImportError")
    assert _imports_symbol(tree, "app.services.analytics_import_adapter", "build_analytics_import")
    assert _calls_symbol(tree, "AnalyticsImportRequest")
    assert _calls_symbol(tree, "build_analytics_import")


def test_f55_page_has_productive_upload_action_and_is_not_shell_only():
    source = _source()
    assert "st.file_uploader(" in source
    assert "Validar y preparar datos de Analytics" in source
    assert 'type=["csv", "json"]' in source
    assert "Esta fase expone su contrato por API" not in source


def test_f55_page_does_not_expose_server_paths_or_duplicate_backend_parser():
    source = _source()
    forbidden = (
        "csv.DictReader",
        "json.loads",
        "open(user_path",
        "Path(user_input",
        "requests.",
        "httpx.",
        "urllib.",
        "pickle.",
        "eval(",
        "exec(",
    )
    for marker in forbidden:
        assert marker not in source, marker


def test_f55_page_is_mobile_safe_and_keeps_technical_details_secondary():
    source = _source()
    assert "st.columns(" not in source
    assert "st.dataframe(" not in source
    assert 'st.expander("Detalles técnicos", expanded=False)' in source
    assert 'st.code(f"{type(exc).__name__}: {exc}", language=None)' in source
    assert "No se han podido validar los datos de Analytics" in source
    assert "UI_PREVIEW_LIMIT = 20" in source


def test_f55_page_does_not_invent_partial_import_or_semantic_promotion():
    source = _source()
    assert "IMPORT_PARTIAL" not in source
    assert "Filas rechazadas" not in source
    assert "VERIFIED_PLATFORM_SEMANTICS" not in source
    assert "MANUAL_SEMANTIC_LABEL" not in source
    assert "cross_platform_equivalence" not in source


def test_f55_page_introduces_no_persistence_publication_or_external_routes():
    source = _source()
    forbidden = (
        "ArtifactStore",
        "sqlite3",
        "upload_file",
        "webhook",
        "mark_published",
        "authorization_to_publish",
        "build_analytics_brain(",
        "build_metric_normalizer(",
    )
    for marker in forbidden:
        assert marker not in source, marker


def test_f55_real_service_csv_flow_is_import_ready():
    payload = (
        "content_id,native_metric_name,value,value_type,observed_at_utc\n"
        "abc,views,123,COUNT,2026-08-22T20:00:00+02:00\n"
    )
    result = build_analytics_import(
        AnalyticsImportRequest(
            format=AnalyticsImportFormat.CSV,
            payload_text=payload,
            default_platform=AnalyticsPlatform.YOUTUBE,
        )
    )
    assert result.status == AnalyticsImportStatus.IMPORT_READY
    assert result.row_count == 1
    assert result.observation_count == 1
    assert result.analytics_request.observations == result.observations


def test_f55_real_service_json_flow_is_import_ready():
    payload = """[
      {
        "platform": "INSTAGRAM",
        "content_id": "post-1",
        "native_metric_name": "retention",
        "value": 0.73,
        "value_type": "RATIO",
        "observed_at_utc": "2026-08-22T18:00:00Z"
      }
    ]"""
    result = build_analytics_import(
        AnalyticsImportRequest(format=AnalyticsImportFormat.JSON, payload_text=payload)
    )
    assert result.status == AnalyticsImportStatus.IMPORT_READY
    assert result.observation_count == 1


def test_f55_real_service_rejects_naive_timestamp_fail_closed():
    payload = (
        "content_id,native_metric_name,value,value_type,observed_at_utc\n"
        "abc,views,123,COUNT,2026-08-22T20:00:00\n"
    )
    with pytest.raises(AnalyticsImportError, match="explicit timezone"):
        build_analytics_import(
            AnalyticsImportRequest(
                format=AnalyticsImportFormat.CSV,
                payload_text=payload,
                default_platform=AnalyticsPlatform.YOUTUBE,
            )
        )


def test_f55_real_service_all_or_nothing_on_row_error():
    payload = (
        "content_id,native_metric_name,value,value_type,observed_at_utc\n"
        "ok,views,10,COUNT,2026-08-22T18:00:00Z\n"
        "bad,views,-1,COUNT,2026-08-22T18:00:00Z\n"
    )
    with pytest.raises(AnalyticsImportError, match=r"row 2:"):
        build_analytics_import(
            AnalyticsImportRequest(
                format=AnalyticsImportFormat.CSV,
                payload_text=payload,
                default_platform=AnalyticsPlatform.YOUTUBE,
            )
        )
