from __future__ import annotations

from html import escape
from typing import Any, Iterable, Mapping

import streamlit as st


_STATE_LABELS = {
    "NEW": "Nuevo",
    "NEEDS_INPUT": "Necesita información",
    "RESEARCHING": "Investigando",
    "SCRIPTING": "Preparando guion",
    "MEDIA": "Seleccionando medios",
    "VOICE": "Preparando voz",
    "VIDEO": "Montando vídeo",
    "READY_FOR_HUMAN_REVIEW": "Listo para revisión",
    "CHANGES_REQUESTED": "Cambios solicitados",
    "FINAL_APPROVED": "Aprobado",
    "PUBLICATION_PACKAGE_READY": "Listo para publicación manual",
    "BLOCKED": "Bloqueado",
    "FAILED": "Requiere atención",
}

_STATE_TONES = {
    "READY_FOR_HUMAN_REVIEW": "review",
    "FINAL_APPROVED": "success",
    "PUBLICATION_PACKAGE_READY": "success",
    "BLOCKED": "danger",
    "FAILED": "danger",
    "CHANGES_REQUESTED": "warning",
    "NEEDS_INPUT": "warning",
}

_PIPELINE = (
    ("Idea", ("NEW", "NEEDS_INPUT")),
    ("Investigación", ("RESEARCH", "RESEARCHING")),
    ("Guion", ("SCRIPT", "SCRIPTING")),
    ("Materiales", ("MEDIA",)),
    ("Producción", ("VOICE", "TTS", "AUDIO", "VIDEO", "VIDEO_BASE", "FINAL_RENDER")),
    ("Revisión", ("READY_FOR_HUMAN_REVIEW", "FINAL_APPROVED", "CHANGES_REQUESTED")),
    ("Paquete", ("PUBLICATION_PACKAGE",)),
    ("Publicación manual", ("PUBLICATION_PACKAGE_READY",)),
)


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip()


def state_display(value: Any) -> str:
    raw = _enum_value(value)
    return _STATE_LABELS.get(raw, raw.replace("_", " ").title() if raw else "—")


def short_identifier(value: Any, *, head: int = 8, tail: int = 6) -> str:
    text = str(value or "—")
    if text == "—" or len(text) <= head + tail + 1:
        return text
    return f"{text[:head]}…{text[-tail:]}"


def render_brand_hero(
    title: str,
    subtitle: str,
    *,
    eyebrow: str = "EL CENTINELA DEL UNIVERSO",
    action_hint: str | None = None,
) -> None:
    safe_eyebrow = escape(eyebrow)
    safe_title = escape(title)
    safe_subtitle = escape(subtitle)
    hint = (
        f'<div class="centinela-hero__hint">{escape(action_hint)}</div>'
        if action_hint
        else ""
    )
    st.html(
        f"""
        <section class="centinela-hero">
          <div class="centinela-hero__sky" aria-hidden="true"></div>
          <div class="centinela-hero__content">
            <div class="centinela-eyebrow">{safe_eyebrow}</div>
            <h1>{safe_title}</h1>
            <p>{safe_subtitle}</p>
            {hint}
          </div>
        </section>
        """
    )


def render_section_heading(
    title: str,
    caption: str | None = None,
    *,
    eyebrow: str | None = None,
) -> None:
    if eyebrow:
        st.html(
            f'<div class="centinela-eyebrow centinela-eyebrow--section">'
            f"{escape(eyebrow)}</div>"
        )
    st.subheader(title)
    if caption:
        st.caption(caption)


def render_state_badge(value: Any) -> None:
    raw = _enum_value(value)
    label = state_display(raw)
    tone = _STATE_TONES.get(raw, "neutral")
    st.html(
        f'<span class="centinela-badge centinela-badge--{tone}">'
        f"{escape(label)}</span>"
    )


def render_empty_state(title: str, message: str, *, action: str | None = None) -> None:
    action_markup = (
        f'<div class="centinela-empty__action">{escape(action)}</div>' if action else ""
    )
    st.html(
        f"""
        <div class="centinela-empty">
          <div class="centinela-empty__orb" aria-hidden="true">✦</div>
          <div>
            <strong>{escape(title)}</strong>
            <p>{escape(message)}</p>
            {action_markup}
          </div>
        </div>
        """
    )


def render_project_timeline(project: Any) -> None:
    """Render the production path with native Streamlit elements.

    This intentionally avoids user-visible raw HTML. The prior grid implementation was
    vulnerable to mobile Markdown/HTML rendering quirks and could expose markup literally.
    """
    state = _enum_value(getattr(project, "state", ""))
    next_stage = _enum_value(getattr(project, "next_stage", ""))
    current_index = 0

    for index, (_, markers) in enumerate(_PIPELINE):
        if state in markers or next_stage in markers:
            current_index = index
            break
    else:
        if state == "FINAL_APPROVED":
            current_index = 6
        elif state == "PUBLICATION_PACKAGE_READY":
            current_index = 7

    completed_through = max(-1, current_index - 1)
    if state == "FINAL_APPROVED":
        completed_through = max(completed_through, 5)
    elif state == "PUBLICATION_PACKAGE_READY":
        completed_through = 7

    current_label = _PIPELINE[current_index][0]
    completed_count = min(len(_PIPELINE), completed_through + 1)
    if state == "PUBLICATION_PACKAGE_READY":
        completed_count = len(_PIPELINE)

    st.caption("Flujo de producción")
    st.progress(
        completed_count / len(_PIPELINE),
        text=f"Etapa {current_index + 1} de {len(_PIPELINE)} · {current_label}",
    )

    with st.expander("Ver etapas del flujo", expanded=False):
        for index, (label, _) in enumerate(_PIPELINE):
            if index <= completed_through:
                glyph = "✓"
                status = "Completado"
            elif index == current_index:
                glyph = "●"
                status = "Etapa actual"
            else:
                glyph = "○"
                status = "Pendiente"
            st.write(f"{glyph} **{label}** · {status}")


def render_kpi_card(
    label: str,
    value: Any,
    *,
    detail: str | None = None,
    tone: str = "neutral",
) -> None:
    with st.container(border=True):
        st.caption(label.upper())
        st.markdown(f"### {value}")
        if detail:
            st.caption(detail)


def render_key_value_card(
    label: str,
    value: Any,
    *,
    detail: str | None = None,
    technical: bool = False,
) -> None:
    with st.container(border=True):
        st.caption(label)
        if technical:
            st.code(str(value if value not in {None, ""} else "—"), language=None)
        else:
            st.markdown(f"**{value if value not in {None, ''} else '—'}**")
        if detail:
            st.caption(detail)


def render_capability_card(
    label: str,
    *,
    connected: bool,
    backend: str,
    resource: str,
) -> None:
    with st.container(border=True):
        status = "Disponible" if connected else "No disponible"
        icon = "✓" if connected else "!"
        st.markdown(f"### {icon} {label}")
        st.caption(status)
        st.write(f"**Backend:** {backend or '—'}")
        st.write(f"**Capacidad:** {resource or '—'}")


def render_error_state(
    message: str,
    *,
    action: str | None = None,
    technical_detail: Any | None = None,
) -> None:
    st.error(message)
    if action:
        st.caption(action)
    if technical_detail is not None:
        with st.expander("Detalle técnico", expanded=False):
            st.code(str(technical_detail), language=None)


def technical_details(
    rows: Mapping[str, Any] | Iterable[tuple[str, Any]],
    *,
    label: str = "Detalles técnicos",
) -> None:
    items = rows.items() if isinstance(rows, Mapping) else rows
    with st.expander(label):
        for key, value in items:
            st.markdown(f"**{key}**")
            st.code(str(value if value not in {None, ""} else "—"), language=None)


def render_manual_publication_notice() -> None:
    st.html(
        """
        <div class="centinela-notice centinela-notice--manual">
          <div class="centinela-notice__icon" aria-hidden="true">◈</div>
          <div>
            <strong>Publicación manual</strong>
            <p>El Centinela prepara los archivos. Tú decides cuándo y dónde publicarlos.</p>
            <p><strong>Esto no publica nada automáticamente.</strong></p>
          </div>
        </div>
        """
    )
