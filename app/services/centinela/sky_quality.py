from __future__ import annotations

from app.models.observation import SkyQualityContext
from app.models.sky_quality import (
    SkyQualityEvidenceRecord,
    SkyQualityIngestionResult,
    SkyQualitySourceMode,
)


def ingest_sky_quality(
    evidence: SkyQualityEvidenceRecord,
) -> tuple[SkyQualityContext, SkyQualityIngestionResult]:
    """Preserve reported sky-quality values and provenance exactly.

    This function deliberately does *not* convert SQM readings into Bortle
    classes, Bortle classes into SQM, or satellite radiance into either metric.
    Those transformations are model-dependent and would require an explicit,
    independently versioned derivation model with its own provenance.
    """

    warnings: list[str] = []

    if evidence.source_mode == SkyQualitySourceMode.MANUAL_BORTLE:
        warnings.append(
            "BORTLE_IS_OBSERVER_CLASSIFICATION_NOT_INSTRUMENTAL_MEASUREMENT"
        )
    elif evidence.source_mode in {
        SkyQualitySourceMode.MAP_DERIVED_SQM,
        SkyQualitySourceMode.MAP_DERIVED_BORTLE,
    }:
        warnings.append("MAP_DERIVED_SKY_QUALITY_IS_NOT_GROUND_TRUTH")

    if evidence.sqm_mag_arcsec2 is not None and evidence.bortle_class is not None:
        warnings.append("SQM_AND_BORTLE_PRESERVED_AS_INDEPENDENT_REPORTED_VALUES")

    context = SkyQualityContext(
        source_id=evidence.source_id,
        evidence_kind=evidence.evidence_kind,
        sqm_mag_arcsec2=evidence.sqm_mag_arcsec2,
        bortle_class=evidence.bortle_class,
    )

    provenance_parts = [
        f"mode={evidence.source_mode.value}",
        f"source={evidence.source_id}",
        f"lat={evidence.latitude_deg:.6f}",
        f"lon={evidence.longitude_deg:.6f}",
    ]
    if evidence.dataset_id:
        provenance_parts.append(f"dataset={evidence.dataset_id}")
    if evidence.dataset_version:
        provenance_parts.append(f"dataset_version={evidence.dataset_version}")
    if evidence.dataset_period:
        provenance_parts.append(f"dataset_period={evidence.dataset_period}")
    if evidence.instrument_model:
        provenance_parts.append(f"instrument={evidence.instrument_model}")
    if evidence.calibration_reference:
        provenance_parts.append(
            f"calibration_reference={evidence.calibration_reference}"
        )

    result = SkyQualityIngestionResult(
        source_id=evidence.source_id,
        evidence_kind=evidence.evidence_kind,
        sqm_mag_arcsec2=evidence.sqm_mag_arcsec2,
        bortle_class=evidence.bortle_class,
        observed_at=evidence.observed_at,
        retrieved_at=evidence.retrieved_at,
        warnings=warnings,
        provenance_summary="; ".join(provenance_parts),
    )
    return context, result
