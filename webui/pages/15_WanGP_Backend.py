from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.wangp_backend import WanGPBackendAuditor  # noqa: E402


st.set_page_config(
    page_title="WanGP Backend Audit · El Centinela",
    layout="wide",
)
st.title("WanGP Backend Audit · El Centinela del Universo")
st.caption(
    "F15 · Auditoría local sin modificar WanGP, sin red y sin descargar modelos."
)

path = st.text_input("Ruta WanGP", r"E:\IA\WanGP")

if st.button("Auditar WanGP", type="primary"):
    result = WanGPBackendAuditor().audit(path)

    a, b, c, d = st.columns(4)
    a.metric("Readiness", result.readiness.value)
    b.metric("Adapter", result.adapter_mode.value)
    c.metric("Model files", result.model_inventory.file_count)
    d.metric(
        "VRAM MiB",
        result.gpu.memory_total_mib
        if result.gpu.memory_total_mib is not None
        else "N/A",
    )

    st.warning(
        "F15 no selecciona ni descarga modelos. La elección I2V y cualquier "
        "descarga grande requieren aprobación posterior."
    )
    st.json(result.model_dump(mode="json"))
