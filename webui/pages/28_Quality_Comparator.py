from __future__ import annotations

import json

import streamlit as st

from app.models.media_mining import MediaMiningPlan
from app.models.quality_comparator import (
    QualityComparatorRequest,
    QualityComparisonStatus,
)
from app.models.selective_upscaling import SelectiveUpscalingPlan
from app.models.shot_quality import ShotQualityPlan
from app.services.quality_comparator import QualityComparatorError, build_quality_comparator


st.set_page_config(page_title="F28 · El Centinela", layout="wide")
st.title("F28 · Quality Comparator")
st.caption(
    "Integra F9 + F26 + F27 para decidir qué escenas mantienen baseline y cuáles "
    "necesitan una comparación A/B humana. F28 nunca selecciona ganador."
)

st.info(
    "**Frontera humana:** un candidato de mejora sólo llega a "
    "A_B_COMPARISON_REQUIRED. El resultado final de la comparación no se fabrica."
)

quality_file = st.file_uploader(
    "F9 · ShotQualityPlan JSON",
    type=["json"],
    key="f28-shot-quality",
)
upscaling_file = st.file_uploader(
    "F26 · SelectiveUpscalingPlan JSON",
    type=["json"],
    key="f28-upscaling",
)
mining_file = st.file_uploader(
    "F27 · MediaMiningPlan JSON",
    type=["json"],
    key="f28-mining",
)


def _load(uploaded, model, label: str):
    if uploaded is None:
        raise QualityComparatorError(f"falta {label}")
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    return model.model_validate(payload)


def _render(plan) -> None:
    st.success("Plan F28 construido. No se ha ejecutado A/B ni seleccionado ganador.")
    st.metric("Escenas", plan.scene_count)
    st.metric("Baseline aceptado", plan.baseline_accepted_count)
    st.metric("A/B pendiente", plan.ab_required_count)
    st.metric("Fallos upstream", plan.failed_count)

    if plan.ab_required_count:
        st.warning(
            "HUMAN REVIEW REQUIRED · Hay candidatos A/B. F28 no puede decidir ganador "
            "ni sustituir la revisión de fidelidad astronómica."
        )

    st.subheader("Comparación contractual por escena")
    for scene in plan.scenes:
        with st.container(border=True):
            st.markdown(f"### Escena {scene.scene_number}")
            st.write(f"Estado: {scene.status.value}")
            st.write(
                "Baseline score: "
                + (f"{scene.baseline_score:.3f}" if scene.baseline_score is not None else "—")
            )
            if scene.status == QualityComparisonStatus.A_B_COMPARISON_REQUIRED:
                st.write(f"Candidato: {scene.candidate_name or '—'}")
                st.write("Ganador: ninguno")
                st.write(
                    "Revisión humana requerida: "
                    + ("sí" if scene.human_review_required else "no")
                )
                st.write(
                    "Fidelidad astronómica requerida: "
                    + ("sí" if scene.astronomy_fidelity_required else "no")
                )
            if scene.warnings:
                st.caption(" · ".join(scene.warnings))

    with st.expander("Detalles técnicos", expanded=False):
        st.write(f"Hash F28: {plan.quality_comparator_hash}")
        st.write(f"Generated UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")
        st.write(f"Executes A/B comparison: {plan.executes_ab_comparison}")
        st.write(f"Selects winner: {plan.selects_winner}")
        st.write(f"Analyzes new frames: {plan.analyzes_new_frames}")
        st.write(f"Modifies media: {plan.modifies_media}")
        st.write(f"GPU required: {plan.gpu_required}")
        st.write(f"Auto publication: {plan.auto_publication}")


if st.button("Construir plan F28", type="primary"):
    try:
        request = QualityComparatorRequest(
            shot_quality=_load(quality_file, ShotQualityPlan, "F9 ShotQualityPlan"),
            upscaling=_load(
                upscaling_file,
                SelectiveUpscalingPlan,
                "F26 SelectiveUpscalingPlan",
            ),
            media_mining=_load(mining_file, MediaMiningPlan, "F27 MediaMiningPlan"),
        )
        _render(build_quality_comparator(request))
    except Exception as exc:
        st.error(
            "No se ha podido construir el plan F28. "
            "No se ha seleccionado ganador ni modificado media."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
