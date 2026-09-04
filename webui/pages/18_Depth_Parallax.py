from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.depth_parallax import DepthMapHint, DepthParallaxRequest  # noqa: E402
from app.models.smart_ken_burns import SmartKenBurnsPlan  # noqa: E402
from app.models.visual_story_graph import VisualStoryGraph  # noqa: E402
from app.services.depth_parallax import build_depth_parallax  # noqa: E402


st.set_page_config(page_title="Depth / Parallax · El Centinela", layout="wide")
st.title("Depth / Parallax · El Centinela del Universo")
st.caption(
    "F18 · Planifica parallax sólo para imágenes estáticas con depth maps "
    "explícitos. No estima profundidad, no usa GPU y no renderiza."
)

graph_path = st.text_input(
    "VisualStoryGraph F8",
    r"E:\IA\MPT-Phase8-Evidence\20260821-214354\real-visual-story-graph.json",
)
ken_path = st.text_input(
    "SmartKenBurnsPlan F13",
    r"E:\IA\MPT-Phase13-Evidence\20260821-224621\real-smart-ken-burns-plan.json",
)
depth_maps_path = st.text_input(
    "Artefacto DepthMapHint[] (opcional)",
    "",
    help=(
        "JSON con una lista de DepthMapHint o un objeto con clave depth_maps. "
        "Si falta, F18 marcará las imágenes que requieren un depth map."
    ),
)
save_path = st.text_input("Guardar DepthParallaxPlan (opcional)", "")


def _load_depth_maps(path_value: str) -> list[DepthMapHint]:
    if not path_value.strip():
        return []
    payload = json.loads(Path(path_value.strip()).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("depth_maps")
    if not isinstance(payload, list):
        raise ValueError(
            "El artefacto de depth maps debe ser una lista o contener depth_maps."
        )
    return [DepthMapHint.model_validate(item) for item in payload]


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido planificar profundidad/parallax. "
        "Revisa los artefactos F8/F13 y los depth maps o consulta los detalles técnicos."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "Evidencia diagnóstica preservada. "
            "No se ha inferido profundidad ni se ha fabricado ningún resultado."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


def _save_result(result) -> None:
    if not save_path.strip():
        return
    target = Path(save_path.strip())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    st.success(f"Plan guardado: {target}")


if st.button("Planificar profundidad / parallax", type="primary"):
    try:
        graph = VisualStoryGraph.model_validate_json(
            Path(graph_path).read_text(encoding="utf-8")
        )
        ken = SmartKenBurnsPlan.model_validate_json(
            Path(ken_path).read_text(encoding="utf-8")
        )
        request = DepthParallaxRequest(
            story_graph=graph,
            ken_burns=ken,
            depth_maps=_load_depth_maps(depth_maps_path),
        )
        result = build_depth_parallax(request)

        st.success("Plan de profundidad/parallax creado.")
        st.metric("Escenas", result.scene_count)
        st.metric("Depth map listo", result.depth_map_ready_count)
        st.metric("Depth map requerido", result.depth_map_required_count)
        st.metric("Revisión requerida", result.review_required_count)

        if result.depth_map_required_count:
            st.warning(
                "Hay imágenes sin depth map explícito. F18 permanece bloqueado "
                "para esas escenas y no ejecuta estimación automática."
            )

        for scene in result.scenes:
            with st.expander(
                f"Escena {scene.scene_number} · {scene.status.value}",
                expanded=False,
            ):
                st.caption(f"Nodo: {scene.node_id}")
                st.write(
                    f"Media seleccionada: {scene.selected_media_id or '—'} "
                    f"· Tipo: {scene.media_type.value if scene.media_type else '—'}"
                )
                st.write(
                    f"Preparada para ejecución posterior: "
                    f"{'sí' if scene.execution_ready else 'no'}"
                )
                if scene.depth_map_path:
                    st.write(f"Depth map: {scene.depth_map_path}")
                    st.write(f"Capas: {scene.layer_count}")
                    st.write(
                        "Desplazamiento parallax máximo: "
                        f"{scene.max_parallax_shift_fraction:.4f}"
                    )
                    st.caption(f"Easing: {scene.easing}")
                if scene.warnings:
                    st.warning(" · ".join(scene.warnings))

        st.info(
            "Planning-only: F18 no ejecuta modelos de depth, no descarga pesos, "
            "no modifica el material y no renderiza."
        )
        _save_result(result)

        with st.expander("Detalles técnicos", expanded=False):
            st.code(result.depth_parallax_hash, language=None)
            st.json(result.structural_checks.model_dump(mode="json"))

    except Exception as exc:
        _render_failure(exc)
