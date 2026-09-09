from __future__ import annotations

from datetime import datetime

from app.models.astrophotography import FramingResult
from app.models.observation import ObservabilityRequest, ObservabilityResult
from app.models.observation_dashboard import (
    DashboardEvidence,
    DashboardMetric,
    ObservationDashboard,
)
from app.models.sky_quality import SkyQualityIngestionResult
from app.services.centinela.open_meteo_observation import weather_snapshot_is_stale


def _state_text(score: float) -> str:
    if score >= 85.0:
        return "EXCELLENT"
    if score >= 70.0:
        return "GOOD"
    if score >= 50.0:
        return "MARGINAL"
    return "POOR"


def _validate_sky_quality_evidence_binding(
    request: ObservabilityRequest,
    evidence: SkyQualityIngestionResult | None,
) -> None:
    if evidence is None:
        return
    if request.sky_quality is None:
        raise ValueError("sky-quality evidence supplied without sky-quality context")
    if evidence.source_id != request.sky_quality.source_id:
        raise ValueError("sky-quality evidence source does not match scoring context")
    if evidence.evidence_kind != request.sky_quality.evidence_kind:
        raise ValueError("sky-quality evidence kind does not match scoring context")
    if evidence.sqm_mag_arcsec2 != request.sky_quality.sqm_mag_arcsec2:
        raise ValueError("sky-quality SQM evidence does not match scoring context")
    if evidence.bortle_class != request.sky_quality.bortle_class:
        raise ValueError("sky-quality Bortle evidence does not match scoring context")


def build_observation_dashboard(
    *,
    title: str,
    request: ObservabilityRequest,
    result: ObservabilityResult,
    now: datetime,
    weather_max_age_hours: float = 3.0,
    framing: FramingResult | None = None,
    sky_quality_evidence: SkyQualityIngestionResult | None = None,
) -> ObservationDashboard:
    """Convert science results into a UI contract without recomputing science."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("dashboard now must be timezone-aware")
    _validate_sky_quality_evidence_binding(request, sky_quality_evidence)

    evidence: list[DashboardEvidence] = []
    attention: list[str] = []

    if request.weather is not None:
        stale = weather_snapshot_is_stale(
            request.weather,
            now=now,
            max_retrieval_age_hours=weather_max_age_hours,
        )
        evidence.append(
            DashboardEvidence(
                source_id=request.weather.source_id,
                evidence_kind=request.weather.evidence_kind.value,
                valid_at=request.weather.valid_at,
                retrieved_at=request.weather.retrieved_at,
                stale=stale,
            )
        )
        if stale:
            attention.append("WEATHER_DATA_STALE")

    if request.astronomy_conditions is not None:
        evidence.append(
            DashboardEvidence(
                source_id=request.astronomy_conditions.source_id,
                evidence_kind=request.astronomy_conditions.evidence_kind.value,
                valid_at=request.astronomy_conditions.valid_at,
                retrieved_at=request.astronomy_conditions.retrieved_at,
                stale=None,
            )
        )

    if request.sky_quality is not None:
        evidence.append(
            DashboardEvidence(
                source_id=request.sky_quality.source_id,
                evidence_kind=request.sky_quality.evidence_kind.value,
                valid_at=(
                    sky_quality_evidence.observed_at
                    if sky_quality_evidence is not None
                    else None
                ),
                retrieved_at=(
                    sky_quality_evidence.retrieved_at
                    if sky_quality_evidence is not None
                    else None
                ),
                stale=None,
            )
        )

    if result.grade == "INSUFFICIENT_DATA":
        attention.append("INSUFFICIENT_DATA")
    if result.missing_inputs:
        attention.append("MISSING_INPUTS")

    metrics = [
        DashboardMetric(
            metric_id=component.name,
            label=component.name.replace("_", " ").title(),
            value_text=f"{component.score:.1f}/100",
            state_text=_state_text(component.score),
            rationale=component.rationale,
            source_ids=component.source_ids,
        )
        for component in result.components
    ]

    available_names = {component.name for component in result.components}
    for missing in result.missing_inputs:
        if missing not in available_names:
            metrics.append(
                DashboardMetric(
                    metric_id=f"missing:{missing}",
                    label=missing.replace("_", " ").title(),
                    value_text="NO DATA",
                    state_text="MISSING",
                    rationale="Input required for a complete observing assessment is unavailable.",
                    available=False,
                )
            )

    framing_summary = None
    mosaic_summary = None
    sampling_summary = None
    if framing is not None:
        framing_summary = (
            f"FOV {framing.horizontal_fov_deg:.2f}° × "
            f"{framing.vertical_fov_deg:.2f}°; target fits="
            f"{framing.target_fits if framing.target_fits is not None else 'UNKNOWN'}"
        )
        if framing.mosaic is not None and framing.mosaic.total_panels > 1:
            mosaic_summary = (
                f"{framing.mosaic.columns}×{framing.mosaic.rows} panels; "
                f"{framing.mosaic.overlap_fraction * 100:.0f}% overlap"
            )
        if framing.sampling_label is not None:
            sampling_summary = framing.sampling_label

    score_text = "NO SCORE" if result.score is None else f"{result.score:.1f}/100"
    return ObservationDashboard(
        title=title,
        grade=result.grade,
        score_text=score_text,
        completeness_text=f"{result.completeness_percent:.1f}% complete",
        completeness_percent=result.completeness_percent,
        attention_required=bool(attention),
        attention_reasons=sorted(set(attention)),
        metrics=metrics,
        evidence=evidence,
        missing_inputs=result.missing_inputs,
        framing_summary=framing_summary,
        mosaic_summary=mosaic_summary,
        sampling_summary=sampling_summary,
        scientific_label=result.scientific_status.value,
    )
