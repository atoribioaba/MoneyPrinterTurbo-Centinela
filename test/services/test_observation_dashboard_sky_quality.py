from datetime import UTC, datetime

import pytest

from app.models.observation import EvidenceKind, ObservationObjectClass, ObservabilityRequest
from app.models.sky_quality import SkyQualityEvidenceRecord, SkyQualitySourceMode
from app.services.centinela.observation_dashboard import build_observation_dashboard
from app.services.centinela.observation_intelligence import evaluate_observability
from app.services.centinela.sky_quality import ingest_sky_quality


NOW = datetime(2026, 9, 9, 20, 0, tzinfo=UTC)


def _record(source_id: str = "sqm:field") -> SkyQualityEvidenceRecord:
    return SkyQualityEvidenceRecord(
        source_id=source_id,
        source_mode=SkyQualitySourceMode.SQM_METER,
        evidence_kind=EvidenceKind.MEASURED,
        latitude_deg=41.6523,
        longitude_deg=-4.7245,
        observed_at=NOW,
        retrieved_at=NOW,
        sqm_mag_arcsec2=20.9,
        instrument_model="SQM-L",
    )


def test_dashboard_preserves_sky_quality_observation_and_retrieval_times():
    sky_context, sky_evidence = ingest_sky_quality(_record())
    request = ObservabilityRequest(
        object_class=ObservationObjectClass.DEEP_SKY,
        target_altitude_deg=60.0,
        sun_altitude_deg=-20.0,
        moon_altitude_deg=-5.0,
        moon_target_separation_deg=120.0,
        moon_illumination_fraction=0.2,
        sky_quality=sky_context,
    )
    dashboard = build_observation_dashboard(
        title="M31",
        request=request,
        result=evaluate_observability(request),
        now=NOW,
        sky_quality_evidence=sky_evidence,
    )

    item = next(e for e in dashboard.evidence if e.source_id == "sqm:field")
    assert item.valid_at == NOW
    assert item.retrieved_at == NOW
    assert item.evidence_kind == "measured"


def test_dashboard_fails_closed_when_sky_quality_provenance_does_not_bind():
    sky_context, _ = ingest_sky_quality(_record("sqm:score"))
    _, mismatched_evidence = ingest_sky_quality(_record("sqm:other"))
    request = ObservabilityRequest(
        object_class=ObservationObjectClass.DEEP_SKY,
        target_altitude_deg=60.0,
        sun_altitude_deg=-20.0,
        moon_altitude_deg=-5.0,
        moon_target_separation_deg=120.0,
        moon_illumination_fraction=0.2,
        sky_quality=sky_context,
    )

    with pytest.raises(ValueError, match="source does not match"):
        build_observation_dashboard(
            title="M31",
            request=request,
            result=evaluate_observability(request),
            now=NOW,
            sky_quality_evidence=mismatched_evidence,
        )
