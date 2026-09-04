from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.astronomy_motion_graphics import AstronomyMotionGraphicsPlan  # noqa: E402
from app.services.cinematic_infographics import build_cinematic_infographics  # noqa: E402


st.set_page_config(
    page_title="Cinematic Infographics · El Centinela",
    layout="wide",
)
st.title("Cinematic Infographics · El Centinela del Universo")
st.caption(
    "F17 · Tarjetas infográficas desde claims ya grounded en F3/F16. "
    "No añade cifras, charts ni datos externos."
)

plan_path = st.text_input(
    "AstronomyVideoPlan F3",
    r"E:\IA\MPT-Phase3-Evidence\20260821-142904\real-astronomy-video-plan.json",
)
graphics_path = st.text_input("AstronomyMotionGraphicsPlan F16", "")
save_path = st.text_input("Guardar CinematicInfographicsPlan (opcional)", "")


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido generar el plan de infografías. "
        "Revisa los artefactos de entrada o consulta los detalles técnicos."
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


if st.button("Planificar infografías", type="primary"):
    try:
        plan = AstronomyVideoPlan.model_validate_json(
            Path(plan_path).read_text(encoding="utf-8")
        )
        graphics = AstronomyMotionGraphicsPlan.model_validate_json(
            Path(graphics_path).read_text(encoding="utf-8")
        )
        result = build_cinematic_infographics(plan, graphics)

        st.success("Plan de infografías creado.")
        st.metric("Tarjetas", result.card_count)
        st.metric("Hechos verificados", result.verified_card_count)
        st.metric("Grounding listo", result.grounding_ready_count)
        st.metric("Revisión humana", result.human_review_required_count)

        for scene in result.scenes:
            with st.expander(
                f"Escena {scene.scene_number} · {scene.card_count} tarjetas",
                expanded=False,
            ):
                if scene.human_review_required:
                    st.warning("La salida infográfica requiere revisión humana.")
                if not scene.cards:
                    st.info("No hay tarjetas planificadas para esta escena.")
                for card in scene.cards:
                    st.markdown(f"**{card.card_type.value} · {card.layout.value}**")
                    st.write(card.statement)
                    st.caption(
                        f"Estado científico: {card.scientific_status.value} · "
                        f"Grounding: {'listo' if card.grounding_ready else 'pendiente'}"
                    )
                    if card.fact_ids:
                        st.caption(f"Fact IDs: {', '.join(card.fact_ids)}")

        st.info(
            "Resultado de planificación únicamente: F17 no crea charts, "
            "no incorpora datos externos y no renderiza vídeo."
        )
        _save_result(result)

        with st.expander("Detalles técnicos", expanded=False):
            st.code(result.infographics_hash, language=None)
            st.json(result.structural_checks.model_dump(mode="json"))

    except Exception as exc:
        _render_failure(exc)
