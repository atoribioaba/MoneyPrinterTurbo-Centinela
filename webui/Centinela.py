from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
WEBUI_ROOT = Path(__file__).resolve().parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui.product import pages, review, studio  # noqa: E402


st.set_page_config(
    page_title="El Centinela del Universo",
    page_icon="☾",
    layout="wide",
    initial_sidebar_state="auto",
)

style_path = WEBUI_ROOT / "product" / "styles.css"
if style_path.is_file():
    st.markdown(f"<style>{style_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

st.sidebar.markdown("## ☾ EL CENTINELA DEL UNIVERSO")
st.sidebar.caption("Studio de producción astronómica")
st.sidebar.caption("Observa · comprende · cuenta el cielo")


def _engineering_title(path: Path) -> str:
    stem = path.stem
    parts = stem.split("_", 1)
    if len(parts) == 2 and parts[0].isdigit():
        stem = parts[1]
    return stem.replace("_", " ")


def _engineering_pages() -> list:
    result = [
        st.Page(
            pages.engineering_page,
            title="Ingeniería · Inicio",
            url_path="ingenieria",
        ),
        st.Page(
            "Main.py",
            title="MoneyPrinterTurbo clásico",
            url_path="mpt-clasico",
        ),
    ]
    for path in sorted((WEBUI_ROOT / "pages").glob("*.py")):
        if path.name.startswith("__"):
            continue
        relative = path.relative_to(WEBUI_ROOT).as_posix()
        result.append(
            st.Page(
                relative,
                title=_engineering_title(path),
            )
        )
    return result


navigation = {
    "ESTUDIO": [
        studio.HOME_PAGE,
        studio.CREATE_PAGE,
        studio.PROJECTS_PAGE,
        st.Page(
            review.review_page,
            title="Revisión",
            url_path="revision",
        ),
        st.Page(
            pages.publication_page,
            title="Publicación",
            url_path="publicacion",
        ),
    ],
    "CIELO": [
        st.Page(
            pages.ephemerides_page,
            title="Agenda y efemérides",
            url_path="cielo",
        ),
        st.Page(
            pages.observatory_page,
            title="Observatorio",
            url_path="observatorio",
        ),
    ],
    "MEDIOS": [
        st.Page(
            pages.library_page,
            title="Biblioteca",
            url_path="biblioteca",
        ),
        st.Page(
            pages.sources_page,
            title="Fuentes y derechos",
            url_path="fuentes",
        ),
    ],
    "MÁS": [
        st.Page(
            pages.analytics_page,
            title="Analítica",
            url_path="analitica",
        ),
        st.Page(
            pages.system_status_page,
            title="Estado del sistema",
            url_path="estado",
        ),
        st.Page(
            pages.settings_page,
            title="Configuración",
            url_path="configuracion",
        ),
    ],
    "INGENIERÍA": _engineering_pages(),
}

page = st.navigation(
    navigation,
    position="sidebar",
    expanded=False,
)
page.run()
