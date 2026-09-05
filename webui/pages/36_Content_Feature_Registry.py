from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.analytics_brain import AnalyticsPlatform  # noqa: E402
from app.models.astronomy_director import AstronomyVideoPlan  # noqa: E402
from app.models.content_feature_registry import (  # noqa: E402
    ContentBinding,
    ContentBindingStatus,
    ContentFeatureRegistryRequest,
)
from app.models.visual_story_graph import VisualStoryGraph  # noqa: E402
from app.services.content_feature_registry import (  # noqa: E402
    build_content_feature_registry,
)


UI_PREVIEW_LIMIT = 20

st.set_page_config(page_title="F36 · El Centinela", layout="wide")
st.title("F36 · Content Feature Registry")
st.caption(
    "Extrae features numéricas con provenance desde F3 + F8. "
    "No almacena el texto creativo completo, no analiza píxeles y no inventa "
    "bindings de plataforma/contenido."
)

uploaded_plan = st.file_uploader(
    "AstronomyVideoPlan de F3 (JSON)",
    type=["json"],
    key="f36_plan",
)
uploaded_graph = st.file_uploader(
    "VisualStoryGraph de F8 (JSON)",
    type=["json"],
    key="f36_graph",
)

bind_content = st.checkbox(
    "Vincular explícitamente este snapshot a contenido publicado",
    value=False,
    help=(
        "El binding es opcional y manual. Si no se confirma, F36 conserva "
        "WAITING_FOR_CONTENT_BINDING."
    ),
)

selected_platform = None
content_id = ""
if bind_content:
    selected_platform = st.selectbox(
        "Plataforma",
        options=list(AnalyticsPlatform),
        format_func=lambda item: item.value,
    )
    content_id = st.text_input(
        "Content ID exacto",
        help="Debe ser el identificador real del contenido en esa plataforma.",
    )


def _render_failure(exc: Exception) -> None:
    st.error(
        "No se ha podido preparar el registro de features. "
        "Comprueba los contratos F3/F8 y, si procede, el binding explícito."
    )
    with st.expander("Detalles técnicos", expanded=False):
        st.caption(
            "F36 falla cerrado: no corrige hashes/contextos, no inventa IDs "
            "y no ejecuta F37 ni fases posteriores."
        )
        st.code(f"{type(exc).__name__}: {exc}", language=None)


if st.button("Preparar registro de features", type="primary"):
    try:
        if uploaded_plan is None:
            raise ValueError("selecciona un AstronomyVideoPlan JSON de F3")
        if uploaded_graph is None:
            raise ValueError("selecciona un VisualStoryGraph JSON de F8")

        plan = AstronomyVideoPlan.model_validate_json(uploaded_plan.getvalue())
        graph = VisualStoryGraph.model_validate_json(uploaded_graph.getvalue())

        binding = None
        if bind_content:
            if selected_platform is None:
                raise ValueError("selecciona una plataforma para el binding")
            normalized_content_id = content_id.strip()
            if not normalized_content_id:
                raise ValueError("indica un content_id real para el binding")
            binding = ContentBinding(
                platform=selected_platform,
                content_id=normalized_content_id,
            )

        result = build_content_feature_registry(
            ContentFeatureRegistryRequest(
                plan=plan,
                story_graph=graph,
                binding=binding,
            )
        )

        st.subheader("Linaje de entrada")
        st.write("Fuente narrativa: F3 · AstronomyVideoPlan")
        st.write("Fuente estructural: F8 · VisualStoryGraph")
        st.write(f"Context hash F3: {result.source_plan_context_hash}")
        st.write(f"Graph hash F8: {result.source_story_graph_hash}")

        if result.status == ContentBindingStatus.WAITING_FOR_CONTENT_BINDING:
            st.warning(
                "Features preparadas sin binding de publicación. "
                "F36 no inventa plataforma ni content_id."
            )
        else:
            st.success(
                "Snapshot ligado explícitamente a contenido mediante el "
                "binding indicado."
            )

        st.metric("Estado", result.status.value)
        st.metric("Snapshots", result.snapshot_count)
        st.metric("Snapshots vinculados", result.bound_snapshot_count)

        st.subheader("Snapshots de features")
        for snapshot_index, snapshot in enumerate(
            result.snapshots[:UI_PREVIEW_LIMIT],
            1,
        ):
            label = f"Snapshot {snapshot_index} · {snapshot.binding_status.value}"
            with st.expander(label, expanded=False):
                if snapshot.platform is not None:
                    st.write(f"Plataforma: {snapshot.platform.value}")
                if snapshot.content_id is not None:
                    st.write(f"Content ID: {snapshot.content_id}")
                st.write(f"Features: {snapshot.feature_count}")
                for feature in snapshot.features:
                    unit = f" {feature.unit}" if feature.unit else ""
                    st.write(f"{feature.feature_name}: {feature.value:g}{unit}")
                    st.caption("Provenance: " + ", ".join(feature.provenance))

        if result.snapshot_count > UI_PREVIEW_LIMIT:
            st.caption(
                f"Mostrando {UI_PREVIEW_LIMIT} de {result.snapshot_count} snapshots."
            )

        st.info(
            "F36 termina en ContentFeatureRegistryPlan. "
            "No ejecuta F37 automáticamente."
        )

        with st.expander("Detalles técnicos", expanded=False):
            st.write(f"Hash F36: {result.content_feature_registry_hash}")
            st.write(f"Generado UTC: {result.generated_at_utc.isoformat()}")
            st.write(f"Planning only: {result.planning_only}")
            st.write(f"Stores creative text: {result.stores_creative_text}")
            st.write(f"Analyzes pixels: {result.analyzes_pixels}")
            st.write(f"Uses LLM: {result.uses_llm}")
            st.write(f"Network calls: {result.network_calls}")
            st.write(f"Database writes: {result.database_writes}")
            st.write(f"Auto publication: {result.auto_publication}")

    except Exception as exc:
        _render_failure(exc)
