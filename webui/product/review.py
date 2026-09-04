from __future__ import annotations

import logging
from datetime import datetime, timezone

import streamlit as st

from app.models.finalization_e2e import (
    HumanFinalReviewDecision,
    HumanFinalReviewRecord,
)
from app.services.centinela.orchestration import ProjectState
from webui.product import pages, ui


LOGGER = logging.getLogger(__name__)


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


def _gate_checkbox(label: str, help_text: str, *, key: str) -> bool:
    with st.container(border=True):
        value = st.checkbox(label, help=help_text, key=key)
        st.caption(help_text)
        return value


def review_page() -> None:
    service = pages._service()

    ui.render_brand_hero(
        "Revisión final humana",
        "Comprueba el trabajo como espectador y valida uno a uno los siete controles que "
        "protegen la calidad científica, audiovisual y editorial.",
        eyebrow="SALA DE REVISIÓN",
        action_hint="NINGÚN CONTROL SE APRUEBA AUTOMÁTICAMENTE",
    )

    project = pages._project_selector(service, "review-selector")
    if project is None:
        ui.render_empty_state(
            "No hay un proyecto para revisar",
            "La sala de revisión se activará cuando una producción llegue a su corte final.",
            action="Continúa el proyecto desde Proyectos.",
        )
        return

    with st.container(border=True):
        st.markdown(f"## {project.title}")
        ui.render_state_badge(project.state)
        ui.render_project_timeline(project)
        st.markdown("### Qué necesita de ti")
        st.write(project.next_action)

    if project.state != ProjectState.READY_FOR_HUMAN_REVIEW:
        st.warning(
            f"Este proyecto está en **{ui.state_display(project.state)}**. "
            "La revisión todavía no está habilitada."
        )
        st.caption(
            "Completa la siguiente etapa desde Proyectos. No se crea ni aprueba ningún "
            "resultado de forma artificial."
        )
        return

    ui.render_section_heading(
        "7 controles antes de aprobar",
        "Marca cada control únicamente después de comprobarlo.",
        eyebrow="CONTROL DE CALIDAD",
    )

    progress_slot = st.empty()

    science_passed = _gate_checkbox(
        "1 · Rigor científico",
        "Datos, afirmaciones, cifras y contexto astronómico verificados.",
        key="review-science",
    )
    visual_passed = _gate_checkbox(
        "2 · Imagen y montaje visual",
        "Selección de planos, continuidad, encuadre y montaje revisados.",
        key="review-visual",
    )
    audio_passed = _gate_checkbox(
        "3 · Audio y locución",
        "Voz, mezcla, niveles y escucha final revisados.",
        key="review-audio",
    )
    subtitles_passed = _gate_checkbox(
        "4 · Subtítulos",
        "Texto, sincronía y legibilidad revisados.",
        key="review-subtitles",
    )
    rights_passed = _gate_checkbox(
        "5 · Derechos y licencias",
        "Procedencia y derechos de los medios confirmados.",
        key="review-rights",
    )
    thumbnail_passed = _gate_checkbox(
        "6 · Miniatura",
        "Portada final revisada y aprobada.",
        key="review-thumbnail",
    )
    copy_passed = _gate_checkbox(
        "7 · Título, caption y textos",
        "Copy editorial final revisado.",
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
    progress_slot.progress(
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

    can_decide = bool(reviewer.strip() and notes.strip())
    if st.button(
        "Solicitar cambios",
        width="stretch",
        disabled=not can_decide,
    ):
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
        except ValueError as exc:
            ui.render_error_state(str(exc))
        except Exception as exc:
            LOGGER.exception("Human review change request failed")
            ui.render_error_state(
                "No se pudo registrar la solicitud de cambios.",
                action="Reintenta la operación o consulta el detalle técnico.",
                technical_detail=exc,
            )

    approve_enabled = can_decide and passed_count == 7
    if st.button(
        "Aprobar proyecto",
        type="primary",
        width="stretch",
        disabled=not approve_enabled,
    ):
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
        except ValueError as exc:
            ui.render_error_state(str(exc))
        except Exception as exc:
            LOGGER.exception("Human review approval failed")
            ui.render_error_state(
                "No se pudo registrar la aprobación.",
                action=(
                    "El proyecto no se ha aprobado. Consulta el detalle técnico si es necesario."
                ),
                technical_detail=exc,
            )

    if not approve_enabled:
        st.caption(
            "Aprobar proyecto se habilita cuando existen notas y los 7/7 controles "
            "están verificados."
        )

    st.info(
        "Aprobar habilita la preparación final del proyecto. "
        "No autoriza ni ejecuta publicación automática en ninguna plataforma."
    )
