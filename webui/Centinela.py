from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
WEBUI_ROOT = Path(__file__).resolve().parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui.product import pages, review  # noqa: E402


st.set_page_config(
    page_title="El Centinela del Universo",
    page_icon="☾",
    layout="wide",
    initial_sidebar_state="expanded",
)

style_path = WEBUI_ROOT / "product" / "styles.css"
if style_path.is_file():
    st.markdown(f"<style>{style_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

st.sidebar.markdown("## ☾ EL CENTINELA DEL UNIVERSO")
st.sidebar.caption("Astronomy Production Studio · Powered by MoneyPrinterTurbo")
st.sidebar.caption("Centinela Edition · pre-V1")


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
        ),
        st.Page(
            "Main.py",
            title="MoneyPrinterTurbo clásico",
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
    "PRODUCCIÓN": [
        st.Page(pages.home_page, title="Inicio", default=True),
        st.Page(pages.create_video_page, title="Crear vídeo"),
        st.Page(pages.projects_page, title="Proyectos"),
        st.Page(review.review_page, title="Revisión"),
    ],
    "ASTRONOMÍA": [
        st.Page(pages.observatory_page, title="Observatorio"),
        st.Page(pages.ephemerides_page, title="Efemérides"),
    ],
    "MEDIOS": [
        st.Page(pages.library_page, title="Biblioteca"),
        st.Page(pages.sources_page, title="Fuentes"),
    ],
    "RESULTADOS": [
        st.Page(pages.publication_page, title="Publicación"),
        st.Page(pages.analytics_page, title="Analítica"),
    ],
    "SISTEMA": [
        st.Page(pages.system_status_page, title="Estado"),
        st.Page(pages.settings_page, title="Configuración"),
    ],
    "AVANZADO · INGENIERÍA": _engineering_pages(),
}

page = st.navigation(
    navigation,
    position="sidebar",
    expanded=False,
)
page.run()
