from __future__ import annotations

import json

import streamlit as st

from app.models.shot_matching import ShotMatchingPlan
from app.models.transition_director import (
    TransitionDirectorRequest,
    TransitionStatus,
)
from app.models.visual_story_graph import VisualStoryGraph
from app.services.transition_director import (
    TransitionDirectorError,
    build_transition_director,
)


st.set_page_config(page_title="F21 · El Centinela", layout="wide")
st.title("F21 · Transition Director")
st.caption(
    "Planifica transiciones motivadas a partir de F8 + F20. "
    "No renderiza vídeo, no busca assets y evita transiciones gratuitas."
)

story_file = st.file_uploader(
    "F8 · VisualStoryGraph JSON",
    type=["json"],
    key="f21-story",
)
matching_file = st.file_uploader(
    "F20 · ShotMatchingPlan JSON",
    type=["json"],
    key="f21-matching",
)


def _load(uploaded, model, label: str):
    if uploaded is None:
        raise TransitionDirectorError(f"falta {label}")
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    return model.model_validate(payload)


def _render(plan) -> None:
    if plan.placeholder_pending_count:
        st.warning(
            f"{plan.placeholder_pending_count} transición(es) quedan bloqueadas por media pendiente."
        )
    else:
        st.success("Plan de transiciones listo sin placeholders pendientes.")

    with st.container(horizontal=True, gap="medium"):
        st.metric("Transiciones", plan.transition_count)
        st.metric("Listas", plan.ready_count)
        st.metric("Pendientes", plan.placeholder_pending_count)

    st.subheader("Plan")
    if not plan.transitions:
        st.caption("No hay aristas narrativas que necesiten transición.")
    for item in plan.transitions:
        with st.container(border=True):
            st.markdown(
                f"### Escena {item.source_scene_number} → {item.target_scene_number}"
            )
            st.write(f"Tipo: {item.transition_type.value}")
            st.write(f"Duración: {item.duration_seconds:.2f} s")
            st.write(f"Estado: {item.status.value}")
            st.write(
                "Execution ready: " + ("sí" if item.execution_ready else "no")
            )
            if item.status == TransitionStatus.PLACEHOLDER_PENDING_MEDIA:
                st.caption(
                    "Media pendiente: F21 no fuerza ni fabrica una transición ejecutable."
                )
            if item.warnings:
                st.caption("Warnings: " + ", ".join(item.warnings))

    with st.expander("Trazabilidad y guardrails", expanded=False):
        st.write(f"Hash F21: {plan.transition_director_hash}")
        st.write(f"Generado UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")
        st.write(f"Resource class: {plan.resource_class}")
        st.write(f"Uses LLM: {plan.uses_llm}")
        st.write(f"GPU required: {plan.gpu_required}")
        st.write(f"Renders video: {plan.renders_video}")
        st.write(f"Creates flashy transitions: {plan.creates_flashy_transitions}")
        st.write(f"Searches assets: {plan.searches_assets}")
        st.write(f"Auto publication: {plan.auto_publication}")

    st.caption(
        "F21 sólo produce un plan. La ejecución audiovisual pertenece al renderer downstream."
    )


if st.button("Construir plan de transiciones", type="primary"):
    try:
        request = TransitionDirectorRequest(
            story_graph=_load(story_file, VisualStoryGraph, "F8 VisualStoryGraph"),
            shot_matching=_load(
                matching_file,
                ShotMatchingPlan,
                "F20 ShotMatchingPlan",
            ),
        )
        _render(build_transition_director(request))
    except Exception as exc:
        st.error(
            "No se ha podido construir el plan F21. "
            "No se ha renderizado ni modificado ningún medio."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
