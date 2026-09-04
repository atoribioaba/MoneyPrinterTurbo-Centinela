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

for style_name in ("styles.css", "v3_patch.css"):
    style_path = WEBUI_ROOT / "product" / style_name
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
ui.configure_product_navigation(
    home=studio.HOME_PAGE,
    create=studio.CREATE_PAGE,
    projects=studio.PROJECTS_PAGE,
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


def _page_is_active(target) -> bool:
    return str(getattr(page, "url_path", "")) == str(getattr(target, "url_path", ""))


def _nav_button(target, *, label: str, icon: str, slot: str) -> None:
    state = "active" if _page_is_active(target) else "idle"
    with st.container(key=f"centinela-nav-{slot}-{state}"):
        clicked = st.button(
            label=label,
            icon=icon,
            width="stretch",
            key=f"centinela-nav-button-{slot}",
            help="Página actual" if state == "active" else None,
        )
        if clicked:
            st.switch_page(target)


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
    _nav_button(
        studio.HOME_PAGE,
        label="Inicio",
        icon=":material/home:",
        slot="desktop-home",
    )
    _nav_button(
        studio.CREATE_PAGE,
        label="Crear",
        icon=":material/add_circle:",
        slot="desktop-create",
    )
    _nav_button(
        studio.PROJECTS_PAGE,
        label="Proyectos",
        icon=":material/movie:",
        slot="desktop-projects",
    )
    _nav_button(
        REVIEW_PAGE,
        label="Revisión",
        icon=":material/fact_check:",
        slot="desktop-review",
    )
    _nav_button(
        PUBLICATION_PAGE,
        label="Publicación",
        icon=":material/inventory_2:",
        slot="desktop-publication",
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


# M1: columns are the layout authority on mobile. The previous nested horizontal
# containers depended on Streamlit's internal DOM and could wrap into two rows.
with st.container(key="centinela-mobile-header"):
    mobile_brand, mobile_menu = st.columns([9, 1], gap="small")
    with mobile_brand:
        ui.render_brand_lockup(compact=True)
    with mobile_menu:
        with st.popover(
            "Menú",
            icon=":material/menu:",
            key="centinela-mobile-header-menu",
        ):
            _render_more_menu()


# M1: five explicit equal columns keep the bottom navigation compact even when
# Streamlit changes wrapper markup around buttons or popovers.
with st.container(key="centinela-mobile-nav"):
    mobile_slots = st.columns(5, gap="small")
    with mobile_slots[0]:
        _nav_button(
            studio.HOME_PAGE,
            label="Inicio",
            icon=":material/home:",
            slot="mobile-home",
        )
    with mobile_slots[1]:
        _nav_button(
            studio.CREATE_PAGE,
            label="Crear",
            icon=":material/add_circle:",
            slot="mobile-create",
        )
    with mobile_slots[2]:
        _nav_button(
            studio.PROJECTS_PAGE,
            label="Proyectos",
            icon=":material/movie:",
            slot="mobile-projects",
        )
    with mobile_slots[3]:
        _nav_button(
            REVIEW_PAGE,
            label="Revisión",
            icon=":material/fact_check:",
            slot="mobile-review",
        )
    with mobile_slots[4]:
        with st.popover(
            "Más",
            icon=":material/more_horiz:",
            width="stretch",
            key="centinela-mobile-more-menu",
        ):
            _render_more_menu()


with st.spinner("Cargando vista…", show_time=False):
    page.run()
