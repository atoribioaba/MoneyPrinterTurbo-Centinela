from __future__ import annotations

import json

import streamlit as st

from app.models.media_mining import MediaMiningRequest, MediaMiningStatus
from app.models.shot_quality import ShotQualityPlan
from app.services.media_mining import build_media_mining


st.set_page_config(page_title="F27 · El Centinela", layout="wide")
st.title("F27 · Media Mining")
st.caption(
    "Clasifica qué fuentes pueden tratarse como imagen única y qué vídeos requieren "
    "detección local. F27 no analiza ni divide vídeo."
)

st.info(
    "**Frontera de runtime:** PySceneDetect + AdaptiveDetector son candidatos locales. "
    "El benchmark y la detección real siguen pendientes; no se buscan medios externos."
)

quality_file = st.file_uploader(
    "F9 · ShotQualityPlan JSON",
    type=["json"],
    key="f27-shot-quality",
)


def _load(uploaded, model, label: str):
    if uploaded is None:
        raise ValueError(f"falta {label}")
    payload = json.loads(uploaded.getvalue().decode("utf-8"))
    return model.model_validate(payload)


def _render(plan) -> None:
    st.success("Plan F27 construido. No se ha ejecutado detección ni split de vídeo.")
    st.metric("Escenas", plan.scene_count)
    st.metric("Imagen única", plan.image_single_shot_count)
    st.metric("Detección requerida", plan.video_detection_required_count)
    st.metric("Análisis fallido upstream", plan.analysis_failed_count)

    if plan.video_detection_required_count:
        st.warning(
            "VIDEO_DETECTION_REQUIRED · El plan solicita validación local posterior; "
            "PySceneDetect no se ha ejecutado en esta página."
        )

    st.subheader("Plan por escena")
    for scene in plan.scenes:
        with st.container(border=True):
            st.markdown(f"### Escena {scene.scene_number}")
            st.write(f"Estado: {scene.status.value}")
            st.write(f"Tipo de medio: {scene.media_type.value if scene.media_type else '—'}")
            st.write(f"Fuente: {scene.source_path or '—'}")
            if scene.status == MediaMiningStatus.VIDEO_DETECTION_REQUIRED:
                st.write(f"Detector candidato: {scene.detector}")
                st.write("Detección real ejecutada: no")
                st.caption("Requiere benchmark local antes de cualquier ejecución real.")
            if scene.warnings:
                st.caption(" · ".join(scene.warnings))

    with st.expander("Detalles técnicos", expanded=False):
        st.write(f"Hash F27: {plan.media_mining_hash}")
        st.write(f"Generated UTC: {plan.generated_at_utc.isoformat()}")
        st.write(f"Planning only: {plan.planning_only}")
        st.write(f"Candidate tool: {plan.candidate_tool}")
        st.write(f"Candidate version: {plan.candidate_reference_version}")
        st.write(f"Candidate license: {plan.candidate_license}")
        st.write(f"Candidate detector: {plan.candidate_detector}")
        st.write(f"GPU required: {plan.gpu_required}")
        st.write(f"SceneDetect invocations: {plan.scenedetect_invocations}")
        st.write(f"Analyzes video: {plan.analyzes_video}")
        st.write(f"Splits video: {plan.splits_video}")
        st.write(f"Downloads dependencies: {plan.downloads_dependencies}")
        st.write(f"Modifies sources: {plan.modifies_sources}")
        st.write("Network calls: 0")
        st.write("External asset search: false")
        st.write("Asset selection: false")
        st.write(f"Auto publication: {plan.auto_publication}")


if st.button("Construir plan F27", type="primary"):
    try:
        request = MediaMiningRequest(
            shot_quality=_load(quality_file, ShotQualityPlan, "F9 ShotQualityPlan")
        )
        _render(build_media_mining(request))
    except Exception as exc:
        st.error(
            "No se ha podido construir el plan F27. "
            "No se ha analizado, dividido, buscado ni seleccionado media."
        )
        with st.expander("Detalles técnicos", expanded=False):
            st.code(f"{type(exc).__name__}: {exc}", language=None)
