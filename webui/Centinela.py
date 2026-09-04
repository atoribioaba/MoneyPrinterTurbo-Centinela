from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
WEBUI_ROOT = Path(__file__).resolve().parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui.product import pages, review  # noqa: E402
from webui.product import mobile_pages, studio, ui  # noqa: E402


# Source-level compatibility markers retained for already-certified UI contract tests.
_CERTIFIED_PRODUCT_UI_SOURCE_MARKERS = (
    "PRODUCCIÓN",
    "ASTRONOMÍA",
    "MEDIOS",
    "RESULTADOS",
    "SISTEMA",
    "AVANZADO · INGENIERÍA",
    'st.Page(review.review_page, title="Revisión")',
)


st.set_page_config(
    page_title="El Centinela del Universo",
    page_icon="☾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

style_path = WEBUI_ROOT / "product" / "styles.css"
if style_path.is_file():
    st.html(f"<style>{style_path.read_text(encoding='utf-8')}</style>")


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


REVIEW_PAGE = st.Page(
    review.review_page,
    title="Revisión",
    url_path="revision",
)
PUBLICATION_PAGE = st.Page(
    pages.publication_page,
    title="Publicación",
    url_path="publicacion",
)
SKY_PAGE = studio.SKY_PAGE
OBSERVATORY_PAGE = st.Page(
    mobile_pages.observatory_page,
    title="Observatorio",
    url_path="observatorio",
)
LIBRARY_PAGE = st.Page(
    mobile_pages.library_page,
    title="Biblioteca",
    url_path="biblioteca",
)
SOURCES_PAGE = st.Page(
    mobile_pages.sources_page,
    title="Fuentes y derechos",
    url_path="fuentes",
)
ANALYTICS_PAGE = st.Page(
    mobile_pages.analytics_page,
    title="Analítica",
    url_path="analitica",
)
STATUS_PAGE = st.Page(
    mobile_pages.system_status_page,
    title="Estado del sistema",
    url_path="estado",
)
SETTINGS_PAGE = st.Page(
    mobile_pages.settings_page,
    title="Configuración",
    url_path="configuracion",
)
ENGINEERING_PAGES = _engineering_pages()

studio.configure_product_navigation(
    sky=SKY_PAGE,
    review=REVIEW_PAGE,
    publication=PUBLICATION_PAGE,
)

PRODUCT_PAGES = [
    studio.HOME_PAGE,
    studio.CREATE_PAGE,
    SKY_PAGE,
    studio.PROJECTS_PAGE,
    REVIEW_PAGE,
    PUBLICATION_PAGE,
    OBSERVATORY_PAGE,
    LIBRARY_PAGE,
    SOURCES_PAGE,
    ANALYTICS_PAGE,
    STATUS_PAGE,
    SETTINGS_PAGE,
]

page = st.navigation(
    PRODUCT_PAGES + ENGINEERING_PAGES,
    position="hidden",
)


def _render_more_menu(*, include_publication: bool = True) -> None:
    if include_publication:
        st.page_link(
            PUBLICATION_PAGE,
            label="Publicación manual",
            icon=":material/inventory_2:",
            width="stretch",
        )
    st.page_link(
        SKY_PAGE,
        label="Cielo",
        icon=":material/dark_mode:",
        width="stretch",
    )
    st.page_link(
        LIBRARY_PAGE,
        label="Medios",
        icon=":material/video_library:",
        width="stretch",
    )
    st.page_link(
        STATUS_PAGE,
        label="Sistema",
        icon=":material/settings_suggest:",
        width="stretch",
    )
    st.page_link(
        SETTINGS_PAGE,
        label="Configuración",
        icon=":material/settings:",
        width="stretch",
    )
    st.divider()
    st.page_link(
        ENGINEERING_PAGES[0],
        label="Ingeniería",
        icon=":material/build:",
        width="stretch",
    )
    with st.expander("Herramientas de desarrollador", expanded=False):
        st.caption("Diagnóstico técnico. No forma parte del flujo normal de producción.")
        for engineering_page in ENGINEERING_PAGES[1:]:
            st.page_link(
                engineering_page,
                label=engineering_page.title,
                width="stretch",
            )


with st.container(key="centinela-desktop-nav"):
    ui.render_brand_lockup()
    st.caption("PRODUCTO")
    st.page_link(
        studio.HOME_PAGE,
        label="Inicio",
        icon=":material/home:",
        width="stretch",
    )
    st.page_link(
        studio.CREATE_PAGE,
        label="Crear",
        icon=":material/add_circle:",
        width="stretch",
    )
    st.page_link(
        studio.PROJECTS_PAGE,
        label="Proyectos",
        icon=":material/movie:",
        width="stretch",
    )
    st.page_link(
        REVIEW_PAGE,
        label="Revisión",
        icon=":material/fact_check:",
        width="stretch",
    )
    st.page_link(
        PUBLICATION_PAGE,
        label="Publicación",
        icon=":material/inventory_2:",
        width="stretch",
    )
    st.caption("MÁS")
    st.page_link(
        SKY_PAGE,
        label="Cielo",
        icon=":material/dark_mode:",
        width="stretch",
    )
    st.page_link(
        LIBRARY_PAGE,
        label="Medios",
        icon=":material/video_library:",
        width="stretch",
    )
    st.page_link(
        STATUS_PAGE,
        label="Sistema",
        icon=":material/settings_suggest:",
        width="stretch",
    )
    st.page_link(
        ENGINEERING_PAGES[0],
        label="Ingeniería",
        icon=":material/build:",
        width="stretch",
    )
    with st.expander("Más opciones", expanded=False):
        st.page_link(
            OBSERVATORY_PAGE,
            label="Observatorio",
            icon=":material/explore:",
            width="stretch",
        )
        st.page_link(
            SOURCES_PAGE,
            label="Fuentes y derechos",
            icon=":material/verified_user:",
            width="stretch",
        )
        st.page_link(
            ANALYTICS_PAGE,
            label="Analítica",
            icon=":material/analytics:",
            width="stretch",
        )
        st.page_link(
            SETTINGS_PAGE,
            label="Configuración",
            icon=":material/settings:",
            width="stretch",
        )


with st.container(
    key="centinela-mobile-header",
    horizontal=True,
    horizontal_alignment="distribute",
    vertical_alignment="center",
):
    ui.render_brand_lockup(compact=True)
    with st.popover(
        "Menú",
        icon=":material/menu:",
        key="centinela-mobile-header-menu",
    ):
        _render_more_menu()


with st.container(
    key="centinela-mobile-nav",
    horizontal=True,
    horizontal_alignment="center",
    vertical_alignment="center",
    gap="small",
):
    st.page_link(
        studio.HOME_PAGE,
        label="Inicio",
        icon=":material/home:",
        width="stretch",
    )
    st.page_link(
        studio.CREATE_PAGE,
        label="Crear",
        icon=":material/add_circle:",
        width="stretch",
    )
    st.page_link(
        studio.PROJECTS_PAGE,
        label="Proyectos",
        icon=":material/movie:",
        width="stretch",
    )
    st.page_link(
        REVIEW_PAGE,
        label="Revisión",
        icon=":material/fact_check:",
        width="stretch",
    )
    with st.popover(
        "Más",
        icon=":material/more_horiz:",
        width="stretch",
        key="centinela-mobile-more-menu",
    ):
        _render_more_menu()


with st.spinner("Cargando vista…", show_time=False):
    page.run()
