import sys

from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from app.models.astromedia import (  # noqa: E402
    HashMode,
    IndexRequest,
    SearchRequest,
)

from app.services.astromedia import (  # noqa: E402
    AstroMediaCatalog,
    AstroMediaError,
)


st.set_page_config(
    page_title=("AstroMedia · El Centinela"),
    layout="wide",
)

st.title("AstroMedia · El Centinela del Universo")

st.caption("Fase 4 · catálogo + provenance + derechos · fuente en sólo lectura")


catalog = AstroMediaCatalog()

items = catalog.list_items(False)

active = [item for item in items if item.active]


c1, c2, c3 = st.columns(3)

c1.metric(
    "Items activos",
    len(active),
)

c2.metric(
    "Publicables",
    sum(item.publication_eligible for item in active),
)

c3.metric(
    "Biblioteca",
    "READ ONLY",
)


with st.expander("Actualizar índice"):
    root = st.text_input(
        "Ruta",
        r"D:\ASTRONOMÍA\Medios",
    )

    mode = st.selectbox(
        "Hash",
        [mode.value for mode in HashMode],
    )

    if st.button(
        "Indexar",
        type="primary",
    ):
        try:
            report = catalog.index_library(
                IndexRequest(
                    root=root,
                    hash_mode=(HashMode(mode)),
                )
            )

            st.json(report.model_dump(mode="json"))

        except AstroMediaError as exc:
            st.error(str(exc))


st.subheader("Buscar material")

query = st.text_input(
    "Consulta",
    "Luna Júpiter cielo nocturno",
)

publication_only = st.checkbox(
    "Sólo derechos verificados",
    False,
)


if st.button("Buscar"):
    results = catalog.search(
        SearchRequest(
            query=query,
            publication_eligible_only=(publication_only),
            limit=25,
        )
    )

    for result in results:
        item = result.item

        with st.expander((f"{item.title} · {item.provider.value} · {result.score}")):
            st.write(item.local_path)

            st.write((f"{item.width}×{item.height} · {item.duration_seconds:.2f}s"))

            st.write(
                "Objetos:",
                item.astronomy_objects,
            )

            st.write(
                "Derechos:",
                item.rights_status.value,
                "· publicable:",
                item.publication_eligible,
            )

            st.write(
                "Razones:",
                result.reasons,
            )
