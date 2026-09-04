from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.visual_story_graph import VisualStoryGraph  # noqa: E402
from app.services.astronomy_motion_graphics import build_motion_graphics  # noqa: E402


st.set_page_config(
    page_title="Astronomy Motion Graphics · El Centinela",
    layout="wide",
)
st.title("Astronomy Motion Graphics · El Centinela del Universo")
st.caption(
    "F16 · Planificación científica de overlays desde objetos y claims ya "
    "presentes en F3/F8. No renderiza, no calcula astronomía y no añade datos."
)

plan_path = st.text_input(
    "AstronomyVideoPlan F3",
    r"E:\IA\MPT-Phase3-Evidence\20260821-142904\real-astronomy-video-plan.json",
)
graph_path = st.text_input(
    "VisualStoryGraph F8",
    r"E:\IA\MPT-Phase8-Evidence\20260821-214354\real-visual-story-graph.json",
)
save_path = st.text_input("Guardar AstronomyMotionGraphicsPlan (opcional)", "")


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido generar el plan de motion graphics. "
        "Revisa los datos de entrada o consulta los detalles técnicos."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "Evidencia diagnóstica preservada. "
            "No se ha fabricado ningún resultado."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


def _save_result(result) -> None:
    if not save_path.strip():
        return
    target = Path(save_path.strip())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    st.success(f"Plan guardado: {target}")


if st.button("Planificar motion graphics", type="primary"):
    try:
        plan = AstronomyVideoPlan.model_validate_json(
            Path(plan_path).read_text(encoding="utf-8")
        )
        graph = VisualStoryGraph.model_validate_json(
            Path(graph_path).read_text(encoding="utf-8")
        )
        result = build_motion_graphics(plan, graph)

        st.success("Plan de motion graphics creado.")
        st.metric("Elementos planificados", result.cue_count)
        st.metric("Etiquetas de objetos", result.object_label_count)
        st.metric("Claims científicos", result.claim_callout_count)
        st.metric("Escenas con revisión", result.review_required_count)

        for scene in result.scenes:
            with st.expander(
                f"Escena {scene.scene_number} · {scene.cue_count} elementos",
                expanded=False,
            ):
                st.caption(f"Nodo: {scene.node_id}")
                if scene.review_required:
                    st.warning("Esta escena requiere revisión humana.")
                if not scene.cues:
                    st.info("No hay overlays planificados para esta escena.")
                for cue in scene.cues:
                    st.markdown(f"**{cue.kind.value} · {cue.anchor.value}**")
                    st.write(cue.text)
                    st.caption(
                        f"Timing normalizado: {cue.normalized_start:.2f} → "
                        f"{cue.normalized_end:.2f} · Animación: {cue.animation.value}"
                    )
                    st.caption(
                        f"Estado científico: {cue.scientific_status.value} · "
                        f"Revisión: {'sí' if cue.review_required else 'no'}"
                    )
                    if cue.fact_ids:
                        st.caption(f"Fact IDs: {', '.join(cue.fact_ids)}")

        st.info(
            "Resultado de planificación únicamente: F16 no renderiza gráficos, "
            "no rastrea objetos y no descarga recursos."
        )
        _save_result(result)

        with st.expander("Detalles técnicos", expanded=False):
            st.code(result.motion_graphics_hash, language=None)
            st.json(result.structural_checks.model_dump(mode="json"))

    except Exception as exc:
        _render_failure(exc)
