from __future__ import annotations

import json

import streamlit as st

from app.models.selective_upscaling import SelectiveUpscalingRequest, UpscaleSceneStatus
from app.models.shot_quality import ShotQualityPlan
from app.models.video_base import VideoBasePlan
from app.services.selective_upscaling import SelectiveUpscalingError, build_selective_upscaling


st.set_page_config(page_title="F26 · El Centinela", layout="wide")
st.title("F26 · Selective Upscaling")
st.caption(
    "Identifica qué escenas no necesitan mejora y cuáles requieren comparación A/B. "
    "F26 planifica; no ejecuta super-resolución."
)

st.info(
    "**Frontera de runtime:** Real-ESRGAN-ncnn-vulkan es sólo un candidato local. "
    "No se descarga ningún modelo, no se usa GPU y no se modifica material."
)

video_file = st.file_uploader(
    "F6 · VideoBasePlan JSON",
    type=["json"],
    key="f26-video-base",
)
quality_file = st.file_uploader(
    "F9 · ShotQualityPlan JSON",
    type=["json"],
    key="f26-shot-quality",
)


def _load(uploaded, model, label: str):
    if uploaded is None:
        raise SelectiveUpscalingError(f"falta {label}")
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    return model.model_validate(payload)


def _render(plan) -> None:
    st.success("Plan F26 construido. No se ha ejecutado ningún upscale.")
    st.metric("Escenas", plan.scene_count)
    st.metric("No requieren upscale", plan.not_required_count)
    st.metric("Requieren revisión A/B", plan.candidate_count)
    st.metric("Placeholders", plan.placeholder_count)

    if plan.candidate_count:
        st.warning(
            "A_B_REVIEW_REQUIRED · La candidatura no equivale a una mejora aceptada. "
            "Debe compararse con la fuente y revisar fidelidad astronómica."
        )
    else:
        st.info("No hay candidatos A/B en este plan.")

    st.subheader("Plan por escena")
    for scene in plan.scenes:
        with st.container(border=True):
            st.markdown(f"### Escena {scene.scene_number}")
            st.write(f"Estado: {scene.status.value}")
            st.write(
                f"Fuente: {scene.source_width}×{scene.source_height} · "
                f"Objetivo: {scene.target_width}×{scene.target_height}"
            )
            if scene.status == UpscaleSceneStatus.A_B_REVIEW_REQUIRED:
                st.write(f"Candidato: {scene.candidate_engine or '—'}")
                st.write(
                    "Revisión de fidelidad astronómica: "
                    + ("obligatoria" if scene.astronomy_fidelity_review_required else "no")
                )
                st.caption(
                    "No inventar estrellas, detalle superficial ni estructura astronómica fina."
                )
            if scene.warnings:
                st.caption(" · ".join(scene.warnings))

    st.warning(
        "El candidato no está ejecutado. MODEL_WEIGHTS_LICENSE permanece "
        f"{plan.model_weights_license}."
    )

    with st.expander("Detalles técnicos", expanded=False):
        st.write(f"Hash F26: {plan.selective_upscaling_hash}")
        st.write(f"Generated UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")
        st.write(f"Candidate engine: {plan.candidate_engine}")
        st.write(f"Engine license: {plan.engine_license}")
        st.write(f"Model weights license: {plan.model_weights_license}")
        st.write(f"GPU required: {plan.gpu_required}")
        st.write(f"Runs upscaler: {plan.runs_upscaler}")
        st.write(f"Downloads models: {plan.downloads_models}")
        st.write(f"Renders video: {plan.renders_video}")
        st.write(f"Changes material identity: {plan.changes_material_identity}")
        st.write(f"Invents astronomy detail: {plan.invents_astronomy_detail}")
        st.write(f"Auto publication: {plan.auto_publication}")


if st.button("Construir plan F26", type="primary"):
    try:
        request = SelectiveUpscalingRequest(
            video_base=_load(video_file, VideoBasePlan, "F6 VideoBasePlan"),
            shot_quality=_load(quality_file, ShotQualityPlan, "F9 ShotQualityPlan"),
        )
        _render(build_selective_upscaling(request))
    except Exception as exc:
        st.error(
            "No se ha podido construir el plan F26. "
            "No se ha ejecutado upscale ni modificado material."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
