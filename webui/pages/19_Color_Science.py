from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.color_science import ColorScienceRequest  # noqa: E402
from app.models.depth_parallax import DepthParallaxPlan  # noqa: E402
from app.models.visual_story_graph import VisualStoryGraph  # noqa: E402
from app.services.color_science import build_color_science  # noqa: E402


st.set_page_config(page_title="Color Science · El Centinela", layout="wide")
st.title("Color Science · El Centinela del Universo")
st.caption(
    "F19 · Define un plan de color conservador desde F8/F18. "
    "No analiza píxeles, no aplica LUTs y no renderiza."
)

graph_path = st.text_input(
    "VisualStoryGraph F8",
    r"E:\IA\MPT-Phase8-Evidence\20260821-214354\real-visual-story-graph.json",
)
depth_path = st.text_input("DepthParallaxPlan F18", "")
save_path = st.text_input("Guardar ColorSciencePlan (opcional)", "")


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido generar el plan de Color Science. "
        "Revisa los artefactos F8/F18 o consulta los detalles técnicos."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "Evidencia diagnóstica preservada. "
            "No se ha fabricado ningún resultado ni se ha aplicado ninguna LUT."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


def _save_result(result) -> None:
    if not save_path.strip():
        return
    target = Path(save_path.strip())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    st.success(f"Plan guardado: {target}")


if st.button("Generar plan de Color Science", type="primary"):
    try:
        graph = VisualStoryGraph.model_validate_json(
            Path(graph_path).read_text(encoding="utf-8")
        )
        depth = DepthParallaxPlan.model_validate_json(
            Path(depth_path).read_text(encoding="utf-8")
        )
        result = build_color_science(
            ColorScienceRequest(story_graph=graph, depth_parallax=depth)
        )

        st.success("Plan de Color Science creado.")
        st.metric("Escenas", result.scene_count)
        st.metric("Grade plan listo", result.grade_ready_count)
        st.metric("Placeholders", result.placeholder_count)

        for scene in result.scenes:
            with st.expander(
                f"Escena {scene.scene_number} · {scene.status.value}",
                expanded=False,
            ):
                st.caption(f"Nodo: {scene.node_id} · Mood: {scene.mood.value}")
                if scene.profile is None:
                    st.info("Escena placeholder: no se define tratamiento de color.")
                    continue
                st.markdown(f"**Perfil:** {scene.profile.value}")
                st.write(f"Saturación: {scene.saturation_scale:.3f}")
                st.write(f"Contraste: {scene.contrast_scale:.3f}")
                st.write(f"Highlight rolloff: {scene.highlight_rolloff:.3f}")
                st.write(f"Shadow lift: {scene.shadow_lift:.3f}")
                st.write(f"Balance de blancos: {scene.white_balance_bias}")
                st.caption(
                    "Preservar color astronómico: "
                    f"{'sí' if scene.preserve_astronomy_color else 'no'} · "
                    "Evitar clipping: "
                    f"{'sí' if scene.avoid_clipping else 'no'} · "
                    "Evitar sobresaturación: "
                    f"{'sí' if scene.avoid_oversaturation else 'no'}"
                )

        st.info(
            "Planning-only: F19 no analiza píxeles, no descarga ni aplica LUTs "
            "y no renderiza vídeo."
        )
        _save_result(result)

        with st.expander("Detalles técnicos", expanded=False):
            st.code(result.color_science_hash, language=None)
            st.caption(f"Fuente F18: {result.source_depth_parallax_hash}")

    except Exception as exc:
        _render_failure(exc)
