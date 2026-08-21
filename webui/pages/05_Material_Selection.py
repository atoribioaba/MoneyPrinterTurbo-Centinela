from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.material_selection import MaterialSelectionRequest  # noqa: E402
from app.services.material_selection import (  # noqa: E402
    MaterialSelectionError,
    MaterialSelector,
)


st.set_page_config(
    page_title=("Material Selection · El Centinela"),
    layout="wide",
)

st.title("Material Selection V1 · El Centinela del Universo")

st.caption("Fase 5 · ScenePlan → AstroMedia → selección determinista")

plan_path = st.text_input(
    "AstronomyVideoPlan JSON",
    (
        r"E:\IA\MPT-Phase3-Evidence"
        r"\20260821-142904"
        r"\real-astronomy-video-plan.json"
    ),
)

min_score = st.number_input(
    "Relevancia mínima",
    min_value=0.0,
    max_value=1000.0,
    value=6.0,
    step=1.0,
)

max_alternatives = st.slider(
    "Alternativas por escena",
    0,
    10,
    3,
)

avoid_reuse = st.checkbox(
    "Penalizar reutilización",
    True,
)

allow_ai = st.checkbox(
    "Permitir IA sólo como último recurso",
    True,
)

publication_only = st.checkbox(
    "Sólo derechos ya verificados",
    False,
)


if st.button(
    "Seleccionar material",
    type="primary",
):
    try:
        plan = AstronomyVideoPlan.model_validate_json(
            Path(plan_path).read_text(encoding="utf-8")
        )

        result = MaterialSelector().select_plan(
            MaterialSelectionRequest(
                plan=plan,
                min_relevance_score=min_score,
                max_alternatives=max_alternatives,
                avoid_reuse=avoid_reuse,
                allow_ai_last_resort=allow_ai,
                publication_eligible_only=publication_only,
            )
        )

        st.success(
            (f"{result.selected_count}/{result.scene_count} escenas seleccionadas")
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Seleccionadas",
            result.selected_count,
        )

        c2.metric(
            "Sin resolver",
            result.unresolved_count,
        )

        c3.metric(
            "Overrides",
            result.manual_override_count,
        )

        c4.metric(
            "IA/recreación",
            result.ai_recreation_count,
        )

        for selection in result.selections:
            with st.expander(
                (f"Escena {selection.scene_number} · {selection.status.value}")
            ):
                st.write(
                    "**Requisito visual:**",
                    selection.visual_requirement,
                )

                st.write(
                    "**Consulta:**",
                    selection.query,
                )

                st.write(
                    "**Media ID:**",
                    selection.selected_media_id,
                )

                st.write(
                    "**Ruta:**",
                    selection.selected_local_path,
                )

                st.write(
                    "**Proveedor:**",
                    (
                        selection.selected_provider.value
                        if (selection.selected_provider)
                        else None
                    ),
                )

                st.write(
                    "**Relevancia:**",
                    selection.relevance_score,
                )

                st.write(
                    "**Revisión requerida:**",
                    selection.review_required,
                )

                st.write(
                    "**Razones:**",
                    selection.reasons,
                )

                if selection.alternatives:
                    st.json(
                        [
                            item.model_dump(mode="json")
                            for item in selection.alternatives
                        ]
                    )

    except (
        OSError,
        ValueError,
        MaterialSelectionError,
    ) as exc:
        st.error(str(exc))
