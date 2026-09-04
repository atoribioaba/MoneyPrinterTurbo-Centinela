from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.color_science import ColorSciencePlan  # noqa: E402
from app.models.shot_matching import ShotMatchingRequest  # noqa: E402
from app.models.shot_quality import ShotQualityPlan  # noqa: E402
from app.models.visual_story_graph import VisualStoryGraph  # noqa: E402
from app.services.shot_matching import build_shot_matching  # noqa: E402


st.set_page_config(page_title="Shot Matching · El Centinela", layout="wide")
st.title("Shot Matching · El Centinela del Universo")
st.caption(
    "F20 · Analiza continuidad entre tomas usando F8/F9/F19 ya existentes. "
    "No analiza frames nuevos y no renderiza."
)

graph_path = st.text_input(
    "VisualStoryGraph F8",
    r"E:\IA\MPT-Phase8-Evidence\20260821-214354\real-visual-story-graph.json",
)
quality_path = st.text_input("ShotQualityPlan F9", "")
color_path = st.text_input("ColorSciencePlan F19", "")
save_path = st.text_input("Guardar ShotMatchingPlan (opcional)", "")


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido analizar Shot Matching. "
        "Revisa los artefactos F8/F9/F19 o consulta los detalles técnicos."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "Evidencia diagnóstica preservada. "
            "No se han analizado frames nuevos ni se ha fabricado ningún resultado."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


def _save_result(result) -> None:
    if not save_path.strip():
        return
    target = Path(save_path.strip())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    st.success(f"Plan guardado: {target}")


if st.button("Analizar Shot Matching", type="primary"):
    try:
        graph = VisualStoryGraph.model_validate_json(
            Path(graph_path).read_text(encoding="utf-8")
        )
        quality = ShotQualityPlan.model_validate_json(
            Path(quality_path).read_text(encoding="utf-8")
        )
        color = ColorSciencePlan.model_validate_json(
            Path(color_path).read_text(encoding="utf-8")
        )
        result = build_shot_matching(
            ShotMatchingRequest(
                story_graph=graph,
                shot_quality=quality,
                color_science=color,
            )
        )

        st.success("Plan de Shot Matching creado.")
        st.metric("Transiciones", result.edge_count)
        st.metric("Matching listo", result.match_ready_count)
        st.metric("Métricas no disponibles", result.metrics_unavailable_count)
        st.metric("Revisión requerida", result.review_required_count)

        for edge in result.edges:
            with st.expander(
                f"Escena {edge.source_scene_number} → "
                f"{edge.target_scene_number} · {edge.status.value}",
                expanded=False,
            ):
                st.caption(f"Edge: {edge.edge_id}")
                st.write(
                    "Preparada para ejecución posterior: "
                    f"{'sí' if edge.execution_ready else 'no'}"
                )
                if edge.exposure_offset_ev is not None:
                    st.write(
                        f"Luma origen/destino: {edge.source_y_avg:.2f} / "
                        f"{edge.target_y_avg:.2f}"
                    )
                    st.write(f"Compensación de exposición: {edge.exposure_offset_ev:+.3f} EV")
                    st.write(
                        "Continuidad de perfil: "
                        f"{edge.color_profile_continuity}"
                    )
                if edge.review_required:
                    st.warning("Esta transición requiere revisión humana.")
                if edge.warnings:
                    st.warning(" · ".join(edge.warnings))

        st.info(
            "Planning-only: F20 reutiliza métricas F9 y el plan F19; "
            "no analiza frames nuevos, no busca material y no renderiza."
        )
        _save_result(result)

        with st.expander("Detalles técnicos", expanded=False):
            st.code(result.shot_matching_hash, language=None)
            st.caption(f"Fuente F9: {result.source_quality_hash}")
            st.caption(f"Fuente F19: {result.source_color_science_hash}")

    except Exception as exc:
        _render_failure(exc)
