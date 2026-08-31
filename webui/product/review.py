from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from app.models.finalization_e2e import (
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.services.centinela.orchestration import ProjectState
from webui.product import pages


def _build_review(
    *,
    decision: HumanFinalReviewDecision,
    reviewer: str,
    notes: str,
    science_passed: bool,
    visual_passed: bool,
    audio_passed: bool,
    subtitles_passed: bool,
    rights_passed: bool,
    thumbnail_passed: bool,
    copy_passed: bool,
) -> HumanFinalReviewRecord:
    reviewer_ref = reviewer.strip()
    rationale = notes.strip()
    if not reviewer_ref:
        raise ValueError("El revisor es obligatorio.")
    if not rationale:
        raise ValueError("Las notas de revisión son obligatorias.")
    return HumanFinalReviewRecord(
        decision=decision,
        reviewer_ref=reviewer_ref,
        rationale=rationale,
        decided_at_utc=datetime.now(timezone.utc),
        science_passed=science_passed,
        visual_passed=visual_passed,
        audio_passed=audio_passed,
        subtitles_passed=subtitles_passed,
        rights_passed=rights_passed,
        thumbnail_passed=thumbnail_passed,
        copy_passed=copy_passed,
    )


def review_page() -> None:
    service = pages._service()
    pages._header(
        "Revisión",
        "La aprobación humana es una frontera deliberada y verificable del pipeline.",
    )
    project = pages._project_selector(service, "review-selector")
    if project is None:
        return

    if project.state != ProjectState.READY_FOR_HUMAN_REVIEW:
        st.info(
            f"Este proyecto está en **{project.state_label}**. "
            "La revisión se habilitará cuando exista un vídeo preparado para revisión humana."
        )
        return

    st.warning(
        "La aprobación exige validar explícitamente los siete controles. "
        "Ningún check se completa automáticamente."
    )

    reviewer = st.text_input("Revisor", value="Revisión humana")
    notes = st.text_area(
        "Notas de revisión",
        placeholder="Justificación de la aprobación o cambios requeridos",
    )

    st.subheader("Controles obligatorios")
    c1, c2 = st.columns(2)
    science_passed = c1.checkbox(
        "Rigor científico verificado",
        key="review-science",
    )
    visual_passed = c1.checkbox(
        "Imagen y montaje visual verificados",
        key="review-visual",
    )
    audio_passed = c1.checkbox(
        "Audio y locución verificados",
        key="review-audio",
    )
    subtitles_passed = c1.checkbox(
        "Subtítulos verificados",
        key="review-subtitles",
    )
    rights_passed = c2.checkbox(
        "Derechos y licencias verificados",
        key="review-rights",
    )
    thumbnail_passed = c2.checkbox(
        "Miniatura verificada",
        key="review-thumbnail",
    )
    copy_passed = c2.checkbox(
        "Copy/caption verificado",
        key="review-copy",
    )

    gates = (
        science_passed,
        visual_passed,
        audio_passed,
        subtitles_passed,
        rights_passed,
        thumbnail_passed,
        copy_passed,
    )
    passed_count = sum(gates)
    st.caption(f"Controles superados: {passed_count}/7")

    approve_col, changes_col = st.columns(2)
    if approve_col.button("Aprobar 7/7", type="primary", use_container_width=True):
        try:
            review = _build_review(
                decision=HumanFinalReviewDecision.APPROVE,
                reviewer=reviewer,
                notes=notes,
                science_passed=science_passed,
                visual_passed=visual_passed,
                audio_passed=audio_passed,
                subtitles_passed=subtitles_passed,
                rights_passed=rights_passed,
                thumbnail_passed=thumbnail_passed,
                copy_passed=copy_passed,
            )
            if not review.all_required_gates_passed:
                raise ValueError(
                    "No se puede aprobar: deben superarse los siete controles obligatorios."
                )
            service.review(project.project_id, review=review)
            st.success("Proyecto aprobado con evidencia humana estructurada 7/7.")
        except Exception as exc:
            st.error(str(exc))

    if changes_col.button("Solicitar cambios", use_container_width=True):
        try:
            review = _build_review(
                decision=HumanFinalReviewDecision.CHANGES_REQUESTED,
                reviewer=reviewer,
                notes=notes,
                science_passed=science_passed,
                visual_passed=visual_passed,
                audio_passed=audio_passed,
                subtitles_passed=subtitles_passed,
                rights_passed=rights_passed,
                thumbnail_passed=thumbnail_passed,
                copy_passed=copy_passed,
            )
            service.review(project.project_id, review=review)
            st.warning("El proyecto vuelve a necesitar intervención antes de continuar.")
        except Exception as exc:
            st.error(str(exc))

    st.caption(
        "La aprobación sólo habilita la siguiente etapa interna. "
        "No autoriza ni ejecuta publicación automática."
    )
