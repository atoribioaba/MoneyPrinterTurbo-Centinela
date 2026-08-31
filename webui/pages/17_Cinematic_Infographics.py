from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.astronomy_motion_graphics import (  # noqa: E402
    AstronomyMotionGraphicsPlan,
)
from app.services.cinematic_infographics import (  # noqa: E402
    build_cinematic_infographics,
)


st.set_page_config(
    page_title="Cinematic Infographics · El Centinela",
    layout="wide",
)
st.title("Cinematic Infographics · El Centinela del Universo")
st.caption(
    "F17 · Tarjetas infográficas desde claims ya grounded. "
    "No añade cifras, charts ni datos externos."
)

plan_path = st.text_input(
    "AstronomyVideoPlan F3",
    r"E:\IA\MPT-Phase3-Evidence\20260821-142904\real-astronomy-video-plan.json",
)
graphics_path = st.text_input(
    "AstronomyMotionGraphicsPlan F16",
    "",
)

if st.button("Planificar infografías", type="primary"):
    plan = AstronomyVideoPlan.model_validate_json(
        Path(plan_path).read_text(encoding="utf-8")
    )
    graphics = AstronomyMotionGraphicsPlan.model_validate_json(
        Path(graphics_path).read_text(encoding="utf-8")
    )

    result = build_cinematic_infographics(plan, graphics)

    a, b, c = st.columns(3)
    a.metric("Cards", result.card_count)
    b.metric("Grounding ready", result.grounding_ready_count)
    c.metric("Human review", result.human_review_required_count)

    st.dataframe(
        [
            {
                "scene": card.scene_number,
                "type": card.card_type.value,
                "status": card.scientific_status.value,
                "statement": card.statement,
                "fact_ids": ", ".join(card.fact_ids),
                "grounding_ready": card.grounding_ready,
                "human_review_required": card.human_review_required,
            }
            for scene in result.scenes
            for card in scene.cards
        ],
        use_container_width=True,
    )
    st.code(result.infographics_hash)
