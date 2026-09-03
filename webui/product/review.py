from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from app.models.finalization_e2e import (
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.services.centinela.orchestration import ProjectState
from webui.product import pages, ui


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


def _review_record(
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
    return _build_review(
        decision=decision,
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


def review_page() -> None:
    service = pages._service()

    ui.render_brand_hero(
        "Revisión final humana",
        "Mira el trabajo como espectador y valida, uno a uno, los siete controles que "
        "protegen la calidad científica, audiovisual y editorial.",
        eyebrow="SALA DE REVISIÓN",
        action_hint="NINGÚN CONTROL SE APRUEBA AUTOMÁTICAMENTE",
    )

    project = pages._project_selector(service, "review-selector")
    if project is None:
        ui.render_empty_state(
            "No hay un proyecto para revisar",
            "La sala de revisión se activará cuando una producción llegue a su corte final.",
        )
        return

    with st.container(border=True):
        st.markdown(f"## {project.title}")
        ui.render_state_badge(project.state)
        ui.render_project_timeline(project)

    if project.state != ProjectState.READY_FOR_HUMAN_REVIEW:
        st.info(
            f"Este proyecto está en **{ui.state_display(project.state)}**. "
            "La revisión se abrirá cuando exista un vídeo preparado para decisión humana."
        )
        return

    ui.render_section_heading(
        "7 controles antes de aprobar",
        "Marca cada control solo después de comprobarlo realmente.",
        eyebrow="CONTROL DE CALIDAD",
    )

    with st.container(border=True):
        science_passed = st.checkbox(
            "1 · Rigor científico",
            help="Datos, afirmaciones, cifras y contexto astronómico verificados.",
            key="review-science",
        )
        visual_passed = st.checkbox(
            "2 · Imagen y montaje visual",
            help="Selección de planos, continuidad, encuadre y montaje revisados.",
            key="review-visual",
        )
        audio_passed = st.checkbox(
            "3 · Audio y locución",
            help="Voz, mezcla, niveles y escucha final revisados.",
            key="review-audio",
        )
        subtitles_passed = st.checkbox(
            "4 · Subtítulos",
            help="Texto, sincronía y legibilidad revisados.",
            key="review-subtitles",
        )
        rights_passed = st.checkbox(
            "5 · Derechos y licencias",
            help="Procedencia y derechos de los medios confirmados.",
            key="review-rights",
        )
        thumbnail_passed = st.checkbox(
            "6 · Miniatura",
            help="Portada final revisada y aprobada.",
            key="review-thumbnail",
        )
        copy_passed = st.checkbox(
            "7 · Título, caption y textos",
            help="Copy editorial final revisado.",
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
        st.progress(
            passed_count / 7,
            text=f"{passed_count}/7 controles verificados",
        )

    ui.render_section_heading(
        "Decisión",
        "Deja una justificación clara de la revisión humana.",
    )
    reviewer = st.text_input("Revisor", value="Revisión humana")
    notes = st.text_area(
        "Notas de revisión",
        placeholder="Qué has comprobado, qué funciona y qué debe cambiar si procede.",
        height=120,
    )

    if st.button("Solicitar cambios", width="stretch"):
        try:
            review = _review_record(
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
            st.warning("Cambios solicitados. El proyecto vuelve al flujo de producción.")
        except Exception as exc:
            st.error(str(exc))

    if st.button("Aprobar proyecto", type="primary", width="stretch"):
        try:
            review = _review_record(
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
            st.success("Proyecto aprobado con revisión humana estructurada 7/7.")
        except Exception as exc:
            st.error(str(exc))

    st.caption(
        "Aprobar habilita la preparación final del proyecto. "
        "No autoriza ni ejecuta publicación automática en ninguna plataforma."
    )
