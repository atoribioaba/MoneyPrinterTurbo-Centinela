from datetime import timezone

import pytest

from app.models.analytics_import_adapter import (
    AnalyticsImportFormat,
    AnalyticsImportRequest,
    AnalyticsImportStatus,
)
from app.models.analytics_brain import AnalyticsPlatform, AnalyticsSourceType
from app.services.analytics_import_adapter import (
    AnalyticsImportError,
    build_analytics_import,
)

CSV = """content_id,native_metric_name,value,value_type,observed_at_utc
abc,views,123,COUNT,2026-08-22T20:00:00+02:00
"""


def test_csv_import_to_f31_contract_and_normalizes_utc():
    result = build_analytics_import(
        AnalyticsImportRequest(
            format=AnalyticsImportFormat.CSV,
            payload_text=CSV,
            default_platform=AnalyticsPlatform.YOUTUBE,
        )
    )

    assert result.status == AnalyticsImportStatus.IMPORT_READY
    assert result.row_count == 1
    assert result.observation_count == 1
    observation = result.analytics_request.observations[0]
    assert observation.content_id == "abc"
    assert observation.platform == AnalyticsPlatform.YOUTUBE
    assert observation.observed_at_utc.tzinfo == timezone.utc
    assert observation.observed_at_utc.hour == 18


def test_json_wrapper_import_uses_defaults_and_normalizes_types():
    payload = """{
      "observations": [
        {
          "content_id": "post-1",
          "native_metric_name": "retention",
          "value": "0.73",
          "value_type": "ratio",
          "observed_at_utc": "2026-08-22T18:00:00Z",
          "position_ratio": "0.5",
          "estimated": "sí"
        }
      ]
    }"""
    result = build_analytics_import(
        AnalyticsImportRequest(
            format=AnalyticsImportFormat.JSON,
            payload_text=payload,
            default_platform=AnalyticsPlatform.INSTAGRAM,
            default_source_type=AnalyticsSourceType.MANUAL_ENTRY,
        )
    )

    observation = result.observations[0]
    assert observation.platform == AnalyticsPlatform.INSTAGRAM
    assert observation.source_type == AnalyticsSourceType.MANUAL_ENTRY
    assert observation.value == pytest.approx(0.73)
    assert observation.position_ratio == pytest.approx(0.5)
    assert observation.estimated is True


def test_empty_import_waits_without_any_side_effects():
    result = build_analytics_import(AnalyticsImportRequest())

    assert result.status == AnalyticsImportStatus.WAITING_FOR_IMPORT_DATA
    assert result.row_count == 0
    assert result.observation_count == 0
    assert result.network_calls == 0
    assert result.api_calls == 0
    assert result.database_writes == 0
    assert result.credentials_required is False
    assert result.uses_llm is False
    assert result.auto_publication is False


def test_same_input_produces_same_evidence_hash():
    request = AnalyticsImportRequest(
        format=AnalyticsImportFormat.CSV,
        payload_text=CSV,
        default_platform=AnalyticsPlatform.YOUTUBE,
    )

    first = build_analytics_import(request)
    second = build_analytics_import(request)

    assert first.analytics_import_hash == second.analytics_import_hash


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("{not-json", "invalid JSON"),
        ('{"rows": {"content_id": "x"}}', "JSON must be an array"),
        ('["not-an-object"]', "all import rows must be objects"),
    ],
)
def test_invalid_json_shapes_fail_closed(payload, expected):
    with pytest.raises(AnalyticsImportError, match=expected):
        build_analytics_import(
            AnalyticsImportRequest(
                format=AnalyticsImportFormat.JSON,
                payload_text=payload,
                default_platform=AnalyticsPlatform.YOUTUBE,
            )
        )


def test_missing_platform_fails_closed_with_row_number():
    with pytest.raises(AnalyticsImportError, match=r"row 1: platform is required"):
        build_analytics_import(
            AnalyticsImportRequest(
                format=AnalyticsImportFormat.CSV,
                payload_text=CSV,
            )
        )


def test_naive_timestamp_is_rejected_instead_of_assuming_runner_timezone():
    payload = CSV.replace("2026-08-22T20:00:00+02:00", "2026-08-22T20:00:00")

    with pytest.raises(
        AnalyticsImportError,
        match=r"row 1: observed_at_utc must include an explicit timezone",
    ):
        build_analytics_import(
            AnalyticsImportRequest(
                format=AnalyticsImportFormat.CSV,
                payload_text=payload,
                default_platform=AnalyticsPlatform.YOUTUBE,
            )
        )


@pytest.mark.parametrize(
    ("value", "value_type", "extra_column", "extra_value", "expected"),
    [
        ("-1", "COUNT", "", "", "non-negative metric required"),
        ("101", "PERCENT", "", "", "percent must be 0..100"),
        ("1", "COUNT", ",position_ratio", ",1.1", "less than or equal to 1"),
    ],
)
def test_invalid_metric_semantics_fail_closed(
    value,
    value_type,
    extra_column,
    extra_value,
    expected,
):
    payload = (
        "content_id,native_metric_name,value,value_type,observed_at_utc"
        f"{extra_column}\n"
        f"abc,metric,{value},{value_type},2026-08-22T18:00:00Z{extra_value}\n"
    )

    with pytest.raises(AnalyticsImportError, match=expected):
        build_analytics_import(
            AnalyticsImportRequest(
                format=AnalyticsImportFormat.CSV,
                payload_text=payload,
                default_platform=AnalyticsPlatform.YOUTUBE,
            )
        )


def test_error_does_not_poison_next_valid_import():
    bad = AnalyticsImportRequest(
        format=AnalyticsImportFormat.JSON,
        payload_text="{bad",
        default_platform=AnalyticsPlatform.YOUTUBE,
    )
    with pytest.raises(AnalyticsImportError):
        build_analytics_import(bad)

    good = build_analytics_import(
        AnalyticsImportRequest(
            format=AnalyticsImportFormat.CSV,
            payload_text=CSV,
            default_platform=AnalyticsPlatform.YOUTUBE,
        )
    )
    assert good.status == AnalyticsImportStatus.IMPORT_READY
    assert good.observation_count == 1
