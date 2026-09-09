from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.observation import EvidenceKind
from app.models.sky_quality import SkyQualityEvidenceRecord, SkyQualitySourceMode
from app.services.centinela.sky_quality import ingest_sky_quality


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def test_measured_sqm_requires_measured_evidence_and_observation_time():
    record = SkyQualityEvidenceRecord(
        source_id="sqm:field:001",
        source_mode=SkyQualitySourceMode.SQM_METER,
        evidence_kind=EvidenceKind.MEASURED,
        latitude_deg=41.6523,
        longitude_deg=-4.7245,
        retrieved_at=NOW,
        observed_at=NOW,
        sqm_mag_arcsec2=20.84,
        instrument_model="SQM-L",
        calibration_reference="factory-calibration-sheet",
    )

    context, result = ingest_sky_quality(record)

    assert context.sqm_mag_arcsec2 == 20.84
    assert context.bortle_class is None
    assert result.warnings == []
    assert "instrument=SQM-L" in result.provenance_summary


def test_sqm_is_not_silently_converted_to_bortle():
    record = SkyQualityEvidenceRecord(
        source_id="sqm:field:002",
        source_mode=SkyQualitySourceMode.SQM_METER,
        evidence_kind=EvidenceKind.MEASURED,
        latitude_deg=41.0,
        longitude_deg=-4.0,
        retrieved_at=NOW,
        observed_at=NOW,
        sqm_mag_arcsec2=21.20,
    )

    context, result = ingest_sky_quality(record)

    assert context.sqm_mag_arcsec2 == 21.20
    assert context.bortle_class is None
    assert result.bortle_class is None


def test_manual_bortle_is_inferred_not_measured():
    with pytest.raises(ValidationError):
        SkyQualityEvidenceRecord(
            source_id="observer:bortle",
            source_mode=SkyQualitySourceMode.MANUAL_BORTLE,
            evidence_kind=EvidenceKind.MEASURED,
            latitude_deg=41.0,
            longitude_deg=-4.0,
            retrieved_at=NOW,
            observed_at=NOW,
            bortle_class=4,
        )

    record = SkyQualityEvidenceRecord(
        source_id="observer:bortle",
        source_mode=SkyQualitySourceMode.MANUAL_BORTLE,
        evidence_kind=EvidenceKind.INFERRED,
        latitude_deg=41.0,
        longitude_deg=-4.0,
        retrieved_at=NOW,
        observed_at=NOW,
        bortle_class=4,
    )
    _, result = ingest_sky_quality(record)
    assert "BORTLE_IS_OBSERVER_CLASSIFICATION_NOT_INSTRUMENTAL_MEASUREMENT" in result.warnings


def test_map_derived_values_require_dataset_provenance():
    with pytest.raises(ValidationError):
        SkyQualityEvidenceRecord(
            source_id="map:example",
            source_mode=SkyQualitySourceMode.MAP_DERIVED_SQM,
            evidence_kind=EvidenceKind.MAP_DERIVED,
            latitude_deg=41.0,
            longitude_deg=-4.0,
            retrieved_at=NOW,
            sqm_mag_arcsec2=20.1,
        )

    record = SkyQualityEvidenceRecord(
        source_id="map:example",
        source_mode=SkyQualitySourceMode.MAP_DERIVED_SQM,
        evidence_kind=EvidenceKind.MAP_DERIVED,
        latitude_deg=41.0,
        longitude_deg=-4.0,
        retrieved_at=NOW,
        sqm_mag_arcsec2=20.1,
        dataset_id="example-sky-map",
        dataset_version="v1",
        dataset_period="2025 annual composite",
        derivation_method="provider-published-sqm-layer",
    )

    context, result = ingest_sky_quality(record)
    assert context.sqm_mag_arcsec2 == 20.1
    assert context.bortle_class is None
    assert "MAP_DERIVED_SKY_QUALITY_IS_NOT_GROUND_TRUTH" in result.warnings
    assert "dataset=example-sky-map" in result.provenance_summary


def test_naive_timestamps_are_rejected():
    with pytest.raises(ValidationError):
        SkyQualityEvidenceRecord(
            source_id="sqm:bad-time",
            source_mode=SkyQualitySourceMode.SQM_METER,
            evidence_kind=EvidenceKind.MEASURED,
            latitude_deg=41.0,
            longitude_deg=-4.0,
            retrieved_at=datetime(2026, 9, 9, 12, 0),
            observed_at=NOW,
            sqm_mag_arcsec2=20.0,
        )


def test_dual_reported_values_are_preserved_but_not_derived():
    record = SkyQualityEvidenceRecord(
        source_id="provider:dual",
        source_mode=SkyQualitySourceMode.MAP_DERIVED_SQM,
        evidence_kind=EvidenceKind.MAP_DERIVED,
        latitude_deg=41.0,
        longitude_deg=-4.0,
        retrieved_at=NOW,
        sqm_mag_arcsec2=20.4,
        bortle_class=4,
        dataset_id="provider-layer",
        dataset_period="2026-01",
    )

    context, result = ingest_sky_quality(record)
    assert context.sqm_mag_arcsec2 == 20.4
    assert context.bortle_class == 4
    assert "SQM_AND_BORTLE_PRESERVED_AS_INDEPENDENT_REPORTED_VALUES" in result.warnings
