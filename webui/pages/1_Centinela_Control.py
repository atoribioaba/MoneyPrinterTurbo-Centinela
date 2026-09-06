import os
import sys

import streamlit as st

root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
if root_dir in sys.path:
    sys.path.remove(root_dir)
sys.path.insert(0, root_dir)

from app.services.centinela_control_plane import (  # noqa: E402
    IntegrationStatus,
    get_engineering_inventory,
    inventory_summary,
)


st.set_page_config(
    page_title="Centinela — Centro de control",
    page_icon="🛰️",
    layout="wide",
)

st.title("🛰️ EL CENTINELA DEL UNIVERSO — Centro de control")
st.caption(
    "Vista unificada del estado real de las ingenierías. "
    "La existencia de un módulo no se confunde con estar integrado en el pipeline."
)

st.info(
    "Política permanente: GENERAR → REVISAR → APROBAR → PUBLICAR. "
    "AUTO_PUBLICATION=FALSE. Esta página no publica contenido."
)

summary = inventory_summary()
cols = st.columns(4)
cols[0].metric("Integrado", summary[IntegrationStatus.WIRED.value])
cols[1].metric("Parcial", summary[IntegrationStatus.PARTIAL.value])
cols[2].metric("Disponible sin cablear", summary[IntegrationStatus.AVAILABLE.value])
cols[3].metric("Placeholder", summary[IntegrationStatus.PLACEHOLDER.value])

st.subheader("Pipeline objetivo unificado")
st.code(
    "ASTRONOMÍA → GUION → MATERIAL → VÍDEO → SUBTÍTULOS → AUDIO "
    "→ QUALITY GATES → REVISIÓN HUMANA → PAQUETE DE PUBLICACIÓN",
    language=None,
)

inventory = [item.as_dict() for item in get_engineering_inventory()]
st.dataframe(
    inventory,
    use_container_width=True,
    hide_index=True,
    column_order=(
        "name",
        "role",
        "status",
        "pipeline_stage",
        "module",
        "note",
    ),
)

st.subheader("Interpretación")
st.markdown(
    "- **wired**: el orquestador llama actualmente al componente.\n"
    "- **partial**: integración real, pero incompleta.\n"
    "- **available_not_wired**: existe y es reutilizable, pero no forma parte del flujo por defecto.\n"
    "- **placeholder**: la etapa existe en el orquestador, pero su handler por defecto aún no ejecuta el motor real."
)

not_ready = [
    item.name
    for item in get_engineering_inventory()
    if item.status in {IntegrationStatus.AVAILABLE, IntegrationStatus.PLACEHOLDER}
]
if not_ready:
    st.warning(
        "La unificación todavía no está terminada. Pendientes de cableado real: "
        + ", ".join(not_ready)
    )
else:
    st.success("Todas las ingenierías registradas están cableadas al pipeline.")
